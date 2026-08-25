"""Executable structural and metric contracts for the demonstration database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractCheck:
    name: str
    failure_count: int
    detail: str

    @property
    def passed(self) -> bool:
        return self.failure_count == 0


class ContractViolation(RuntimeError):
    """Raised when one or more executable contracts fail."""

    def __init__(self, failures: list[ContractCheck]):
        self.failures = failures
        summary = ", ".join(
            f"{check.name} ({check.failure_count})" for check in failures
        )
        super().__init__(f"data contracts failed: {summary}")


REQUIRED_COLUMNS = {
    "raw_records": {
        "record_hash",
        "record_type",
        "business_key",
        "version",
        "event_time",
        "recorded_at",
        "payload_json",
        "canonical_json",
    },
    "raw_observations": {
        "observation_id",
        "source_file",
        "source_line",
        "record_hash",
    },
    "stg_delivery_events": {
        "business_key",
        "delivery_id",
        "event_kind",
        "event_time",
        "recorded_at",
        "version",
        "record_hash",
    },
    "mart_delivery_outcomes": {
        "delivery_id",
        "request_time",
        "final_assignment_time",
        "assignment_latency_seconds",
        "outcome",
        "switchback_arm",
    },
    "mart_ledger_reconciliation": {
        "delivery_id",
        "net_minor",
        "reconciliation_status",
        "is_reconciled",
    },
    "mart_geospatial_quality": {
        "delivery_id",
        "pickup_in_zone",
        "distance_plausible",
        "is_valid",
    },
}


COUNT_QUERIES = {
    "observation_references": """
        SELECT COUNT(*)
        FROM raw_observations AS observation
        LEFT JOIN raw_records AS record
          ON record.record_hash = observation.record_hash
        WHERE record.record_hash IS NULL
    """,
    "canonical_record_hashes": """
        SELECT COUNT(*)
        FROM (
            SELECT record_hash, COUNT(*) AS row_count
            FROM raw_records
            GROUP BY record_hash
            HAVING COUNT(*) > 1
        )
    """,
    "delivery_event_keys": """
        SELECT COUNT(*)
        FROM (
            SELECT business_key
            FROM stg_delivery_events
            GROUP BY business_key
            HAVING COUNT(*) > 1
        )
    """,
    "delivery_outcome_keys": """
        SELECT COUNT(*)
        FROM (
            SELECT delivery_id
            FROM mart_delivery_outcomes
            GROUP BY delivery_id
            HAVING COUNT(*) > 1
        )
    """,
    "request_outcome_coverage": """
        WITH requested AS (
            SELECT DISTINCT delivery_id
            FROM stg_delivery_events
            WHERE event_kind = 'requested'
        ),
        differences AS (
            SELECT requested.delivery_id
            FROM requested
            LEFT JOIN mart_delivery_outcomes AS outcome USING (delivery_id)
            WHERE outcome.delivery_id IS NULL
            UNION ALL
            SELECT outcome.delivery_id
            FROM mart_delivery_outcomes AS outcome
            LEFT JOIN requested USING (delivery_id)
            WHERE requested.delivery_id IS NULL
        )
        SELECT COUNT(*) FROM differences
    """,
    "mart_row_coverage": """
        SELECT
            ABS(
                (SELECT COUNT(*) FROM mart_delivery_outcomes)
                - (SELECT COUNT(*) FROM mart_ledger_reconciliation)
            )
            + ABS(
                (SELECT COUNT(*) FROM mart_delivery_outcomes)
                - (SELECT COUNT(*) FROM mart_geospatial_quality)
            )
    """,
    "request_zone_references": """
        SELECT COUNT(*)
        FROM mart_delivery_outcomes AS outcome
        LEFT JOIN stg_zones AS zone ON zone.zone_id = outcome.zone_id
        WHERE zone.zone_id IS NULL
    """,
    "ledger_delivery_references": """
        SELECT COUNT(*)
        FROM stg_ledger_entries AS entry
        LEFT JOIN mart_delivery_outcomes AS outcome
          ON outcome.delivery_id = entry.delivery_id
        WHERE outcome.delivery_id IS NULL
    """,
    "assignment_latency": """
        SELECT COUNT(*)
        FROM mart_delivery_outcomes
        WHERE assignment_latency_seconds < 0
    """,
    "reconstructed_switch_state": """
        SELECT COUNT(*)
        FROM mart_delivery_outcomes
        WHERE switchback_arm NOT IN ('control', 'treatment')
           OR switchback_arm IS NULL
    """,
    "final_assignment_kind": """
        SELECT COUNT(*)
        FROM mart_delivery_outcomes AS outcome
        LEFT JOIN stg_delivery_events AS event
          ON event.business_key = outcome.final_assignment_key
        WHERE outcome.final_assignment_key IS NOT NULL
          AND (event.business_key IS NULL OR event.event_kind <> 'dispatch_accepted')
    """,
    "final_assignment_selection": """
        WITH ranked AS (
            SELECT
                delivery_id,
                business_key,
                ROW_NUMBER() OVER (
                    PARTITION BY delivery_id
                    ORDER BY event_time DESC, recorded_at DESC, business_key DESC
                ) AS event_rank
            FROM stg_delivery_events
            WHERE event_kind = 'dispatch_accepted'
        )
        SELECT COUNT(*)
        FROM ranked
        JOIN mart_delivery_outcomes AS outcome USING (delivery_id)
        WHERE ranked.event_rank = 1
          AND ranked.business_key <> outcome.final_assignment_key
    """,
    "terminal_selection": """
        WITH ranked AS (
            SELECT
                delivery_id,
                business_key,
                event_kind,
                ROW_NUMBER() OVER (
                    PARTITION BY delivery_id
                    ORDER BY event_time DESC, recorded_at DESC, business_key DESC
                ) AS event_rank
            FROM stg_delivery_events
            WHERE event_kind IN ('completed', 'cancelled')
        )
        SELECT COUNT(*)
        FROM ranked
        JOIN mart_delivery_outcomes AS outcome USING (delivery_id)
        WHERE ranked.event_rank = 1
          AND (
              ranked.business_key <> outcome.terminal_event_key
              OR ranked.event_kind <> outcome.outcome
          )
    """,
    "ledger_arithmetic": """
        SELECT COUNT(*)
        FROM mart_ledger_reconciliation
        WHERE net_minor <> base_minor + adjustment_minor + reversal_minor
    """,
    "ledger_status_flags": """
        SELECT COUNT(*)
        FROM mart_ledger_reconciliation
        WHERE (reconciliation_status = 'exception' AND is_reconciled <> 0)
           OR (reconciliation_status IN ('passed', 'not_due') AND is_reconciled <> 1)
           OR (outcome = 'open' AND reconciliation_status <> 'not_due')
           OR (outcome <> 'open' AND reconciliation_status = 'not_due')
    """,
    "geospatial_flags": """
        SELECT COUNT(*)
        FROM mart_geospatial_quality
        WHERE pickup_in_zone NOT IN (0, 1)
           OR distance_plausible NOT IN (0, 1)
           OR is_valid NOT IN (0, 1)
           OR is_valid <> pickup_in_zone * distance_plausible
    """,
    "switchback_singleton": """
        SELECT ABS(COUNT(*) - 1)
        FROM mart_switchback_analysis
    """,
    "switchback_rates": """
        SELECT COUNT(*)
        FROM mart_switchback_analysis
        WHERE control_batched_rate NOT BETWEEN 0.0 AND 1.0
           OR treatment_batched_rate NOT BETWEEN 0.0 AND 1.0
           OR ABS(
               rate_difference - (treatment_batched_rate - control_batched_rate)
           ) > 0.000000001
    """,
    "health_metric_values": """
        WITH expected AS (
            SELECT 'raw_observations' AS metric_name, COUNT(*) AS metric_value
            FROM raw_observations
            UNION ALL
            SELECT 'raw_records', COUNT(*) FROM raw_records
            UNION ALL
            SELECT
                'duplicate_observations',
                COUNT(*) - COUNT(DISTINCT record_hash)
            FROM raw_observations
            UNION ALL
            SELECT
                'late_records',
                COUNT(*)
            FROM raw_records
            WHERE (julianday(recorded_at) - julianday(event_time)) * 86400.0 > 300.0
            UNION ALL
            SELECT 'open_outcomes', COUNT(*)
            FROM mart_delivery_outcomes WHERE outcome = 'open'
            UNION ALL
            SELECT 'terminal_outcomes', COUNT(*)
            FROM mart_delivery_outcomes WHERE outcome IN ('completed', 'cancelled')
            UNION ALL
            SELECT 'ledger_exceptions', COUNT(*)
            FROM mart_ledger_reconciliation WHERE reconciliation_status = 'exception'
            UNION ALL
            SELECT 'geo_exceptions', COUNT(*)
            FROM mart_geospatial_quality WHERE is_valid = 0
            UNION ALL
            SELECT 'corrected_business_keys', COUNT(*)
            FROM (
                SELECT record_type, business_key
                FROM raw_records
                GROUP BY record_type, business_key
                HAVING MAX(version) > 1
            )
        ),
        differences AS (
            SELECT expected.metric_name
            FROM expected
            LEFT JOIN mart_pipeline_health AS actual USING (metric_name)
            WHERE actual.metric_name IS NULL
               OR ABS(actual.metric_value - expected.metric_value) > 0.000000001
            UNION ALL
            SELECT actual.metric_name
            FROM mart_pipeline_health AS actual
            LEFT JOIN expected USING (metric_name)
            WHERE expected.metric_name IS NULL
        )
        SELECT COUNT(*) FROM differences
    """,
}


WINNER_TABLES = {
    "zone": "stg_zones",
    "switch_state": "stg_switch_states",
    "delivery_event": "stg_delivery_events",
    "ledger_entry": "stg_ledger_entries",
}


def _required_column_checks(connection: sqlite3.Connection) -> list[ContractCheck]:
    checks: list[ContractCheck] = []
    for table, required in REQUIRED_COLUMNS.items():
        actual = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = sorted(required.difference(actual))
        checks.append(
            ContractCheck(
                name=f"required_columns:{table}",
                failure_count=len(missing),
                detail="required columns are present",
            )
        )
    return checks


def _winner_check(
    connection: sqlite3.Connection,
    record_type: str,
    staging_table: str,
) -> ContractCheck:
    query = f"""
        WITH ranked AS (
            SELECT
                record_hash,
                ROW_NUMBER() OVER (
                    PARTITION BY record_type, business_key
                    ORDER BY version DESC, recorded_at DESC, record_hash DESC
                ) AS winner_rank
            FROM raw_records
            WHERE record_type = ?
        ),
        differences AS (
            SELECT ranked.record_hash
            FROM ranked
            LEFT JOIN {staging_table} AS staged
              ON staged.record_hash = ranked.record_hash
            WHERE ranked.winner_rank = 1
              AND staged.record_hash IS NULL
            UNION ALL
            SELECT staged.record_hash
            FROM {staging_table} AS staged
            LEFT JOIN ranked
              ON ranked.record_hash = staged.record_hash
             AND ranked.winner_rank = 1
            WHERE ranked.record_hash IS NULL
        )
        SELECT COUNT(*) FROM differences
    """
    failure_count = int(connection.execute(query, (record_type,)).fetchone()[0])
    return ContractCheck(
        name=f"winning_version:{record_type}",
        failure_count=failure_count,
        detail="staging matches version, record-time, and hash ordering",
    )


def run_contracts(connection: sqlite3.Connection) -> list[ContractCheck]:
    """Run every contract and return pass/fail evidence without exposing rows."""

    checks = _required_column_checks(connection)
    for name, query in COUNT_QUERIES.items():
        failure_count = int(connection.execute(query).fetchone()[0])
        checks.append(
            ContractCheck(
                name=name,
                failure_count=failure_count,
                detail="query must return zero failures",
            )
        )
    for record_type, staging_table in WINNER_TABLES.items():
        checks.append(_winner_check(connection, record_type, staging_table))
    return checks


def assert_contracts(connection: sqlite3.Connection) -> list[ContractCheck]:
    """Raise on any contract failure and otherwise return all passing checks."""

    checks = run_contracts(connection)
    failures = [check for check in checks if not check.passed]
    if failures:
        raise ContractViolation(failures)
    return checks
