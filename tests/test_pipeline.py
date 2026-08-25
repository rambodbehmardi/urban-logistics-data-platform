from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from urban_data_platform.contracts import assert_contracts, run_contracts
from urban_data_platform.generate import generate_batches
from urban_data_platform.pipeline import connect_database, normalize_record, run_pipeline


class PipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.paths = generate_batches(self.root / "raw", seed=91_337)
        self.database = self.root / "platform.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _rows(self, table: str, order_by: str) -> list[tuple[object, ...]]:
        connection = connect_database(self.database)
        try:
            return [
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY {order_by}"
                ).fetchall()
            ]
        finally:
            connection.close()

    def test_same_seed_produces_byte_identical_batches(self) -> None:
        with tempfile.TemporaryDirectory() as second_directory:
            other = generate_batches(Path(second_directory), seed=91_337)
            self.assertEqual(
                self.paths["initial"].read_bytes(), other["initial"].read_bytes()
            )
            self.assertEqual(self.paths["late"].read_bytes(), other["late"].read_bytes())

    def test_late_batch_resolves_open_and_corrected_outcomes(self) -> None:
        initial = run_pipeline(self.database, [self.paths["initial"]], reset=True)
        self.assertGreater(initial["open_outcomes"], 0)

        connection = connect_database(self.database)
        try:
            before = connection.execute(
                """
                SELECT event_kind, version
                FROM stg_delivery_events
                WHERE business_key = 'event:delivery-004:terminal'
                """
            ).fetchone()
            self.assertEqual(tuple(before), ("cancelled", 1))
        finally:
            connection.close()

        final = run_pipeline(self.database, [self.paths["late"]])
        self.assertLess(final["open_outcomes"], initial["open_outcomes"])
        self.assertGreater(final["late_records"], 0)
        self.assertEqual(final["corrected_business_keys"], 2)

        connection = connect_database(self.database)
        try:
            after = connection.execute(
                """
                SELECT event_kind, version
                FROM stg_delivery_events
                WHERE business_key = 'event:delivery-004:terminal'
                """
            ).fetchone()
            self.assertEqual(tuple(after), ("completed", 2))
            open_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT delivery_id FROM mart_delivery_outcomes WHERE outcome = 'open'"
                )
            }
            self.assertEqual(open_ids, {"delivery-012"})
        finally:
            connection.close()

    def test_final_assignment_and_request_time_state_are_reconstructed(self) -> None:
        run_pipeline(
            self.database,
            [self.paths["initial"], self.paths["late"]],
            reset=True,
        )
        connection = connect_database(self.database)
        try:
            assignments = {
                row[0]: row[1]
                for row in connection.execute(
                    """
                    SELECT delivery_id, final_assignment_key
                    FROM mart_delivery_outcomes
                    WHERE delivery_id IN ('delivery-003', 'delivery-005')
                    """
                )
            }
            self.assertEqual(
                assignments["delivery-003"], "event:delivery-003:accept-2"
            )
            self.assertEqual(
                assignments["delivery-005"], "event:delivery-005:accept-2"
            )

            arms = {
                row[0]: row[1]
                for row in connection.execute(
                    """
                    SELECT delivery_id, switchback_arm
                    FROM mart_delivery_outcomes
                    WHERE delivery_id IN ('delivery-001', 'delivery-007')
                    """
                )
            }
            self.assertEqual(arms["delivery-001"], "control")
            self.assertEqual(arms["delivery-007"], "treatment")
        finally:
            connection.close()

    def test_replay_is_idempotent_but_duplicate_evidence_is_measurable(self) -> None:
        first = run_pipeline(
            self.database,
            [self.paths["initial"], self.paths["late"]],
            reset=True,
        )
        tables = {
            "raw_records": "record_hash",
            "raw_observations": "observation_id",
            "stg_delivery_events": "business_key",
            "mart_delivery_outcomes": "delivery_id",
            "mart_ledger_reconciliation": "delivery_id",
            "mart_geospatial_quality": "delivery_id",
        }
        before = {
            table: self._rows(table, order_by) for table, order_by in tables.items()
        }

        replay = run_pipeline(
            self.database,
            [self.paths["initial"], self.paths["late"]],
        )
        after = {
            table: self._rows(table, order_by) for table, order_by in tables.items()
        }
        self.assertEqual(before, after)
        self.assertEqual(replay["ingest"]["observations_inserted"], 0)
        self.assertEqual(replay["ingest"]["records_inserted"], 0)
        self.assertGreater(first["duplicate_observations"], 0)

    def test_quality_exceptions_and_switchback_metrics_are_exposed(self) -> None:
        summary = run_pipeline(
            self.database,
            [self.paths["initial"], self.paths["late"]],
            reset=True,
        )
        self.assertGreater(summary["ledger_exceptions"], 0)
        self.assertGreater(summary["geo_exceptions"], 0)
        switchback = summary["switchback"]
        self.assertGreater(switchback["control_count"], 0)
        self.assertGreater(switchback["treatment_count"], 0)
        self.assertGreaterEqual(switchback["control_batched_rate"], 0.0)
        self.assertLessEqual(switchback["control_batched_rate"], 1.0)
        self.assertGreaterEqual(switchback["treatment_batched_rate"], 0.0)
        self.assertLessEqual(switchback["treatment_batched_rate"], 1.0)

        connection = connect_database(self.database)
        try:
            ledger_ids = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT delivery_id
                    FROM mart_ledger_reconciliation
                    WHERE reconciliation_status = 'exception'
                    """
                )
            }
            geo_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT delivery_id FROM mart_geospatial_quality WHERE is_valid = 0"
                )
            }
            self.assertEqual(ledger_ids, {"delivery-007"})
            self.assertEqual(geo_ids, {"delivery-006", "delivery-008"})
        finally:
            connection.close()

    def test_hash_tie_break_is_stable_and_contracts_pass(self) -> None:
        run_pipeline(self.database, [self.paths["initial"]], reset=True)
        tied_records = [
            {
                "business_key": "event:delivery-004:terminal",
                "event_time": "2040-01-01T09:12:00Z",
                "payload": {
                    "delivery_id": "delivery-004",
                    "event_kind": event_kind,
                    "is_batched": True,
                },
                "record_type": "delivery_event",
                "recorded_at": "2040-01-01T12:00:00Z",
                "version": 3,
            }
            for event_kind in ("completed", "cancelled")
        ]
        expected_hash = max(normalize_record(record)[2] for record in tied_records)
        tie_batch = self.root / "raw" / "batch_tie.jsonl"
        tie_batch.write_text(
            "".join(
                json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
                for record in tied_records
            ),
            encoding="utf-8",
        )
        run_pipeline(self.database, [tie_batch])

        connection = connect_database(self.database)
        try:
            selected_hash = connection.execute(
                """
                SELECT record_hash
                FROM stg_delivery_events
                WHERE business_key = 'event:delivery-004:terminal'
                """
            ).fetchone()[0]
            self.assertEqual(selected_hash, expected_hash)
            checks = run_contracts(connection)
            self.assertTrue(all(check.passed for check in checks))
            self.assertEqual(len(assert_contracts(connection)), len(checks))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
