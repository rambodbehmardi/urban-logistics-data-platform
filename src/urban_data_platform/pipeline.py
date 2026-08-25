"""SQLite ingestion, deterministic staging, and analytical rebuilds."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ALLOWED_RECORD_TYPES = {"zone", "switch_state", "delivery_event", "ledger_entry"}
REQUIRED_FIELDS = {
    "record_type",
    "business_key",
    "version",
    "event_time",
    "recorded_at",
    "payload",
}


@dataclass(frozen=True)
class IngestStats:
    files_seen: int
    observations_inserted: int
    records_inserted: int


def _sql_text(filename: str) -> str:
    return (Path(__file__).with_name("sql") / filename).read_text(encoding="utf-8")


def _parse_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO 8601 string")
    if not value.endswith("Z"):
        raise ValueError(f"{field} must use the UTC Z suffix")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset")
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")
    return value


def normalize_record(record: Any) -> tuple[dict[str, Any], str, str]:
    """Validate one envelope and return it with canonical JSON and its digest."""

    if not isinstance(record, dict):
        raise ValueError("record must be a JSON object")
    missing = REQUIRED_FIELDS.difference(record)
    if missing:
        raise ValueError(f"record is missing required fields: {', '.join(sorted(missing))}")
    if record["record_type"] not in ALLOWED_RECORD_TYPES:
        raise ValueError("record_type is not supported")
    if not isinstance(record["business_key"], str) or not record["business_key"].strip():
        raise ValueError("business_key must be a non-empty string")
    if isinstance(record["version"], bool) or not isinstance(record["version"], int):
        raise ValueError("version must be a positive integer")
    if record["version"] <= 0:
        raise ValueError("version must be a positive integer")
    _parse_timestamp(record["event_time"], "event_time")
    _parse_timestamp(record["recorded_at"], "recorded_at")
    if not isinstance(record["payload"], dict):
        raise ValueError("payload must be a JSON object")

    canonical_json = json.dumps(
        record,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    record_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return record, canonical_json, record_hash


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(_sql_text("schema.sql"))


def ingest_jsonl(
    connection: sqlite3.Connection,
    input_paths: Iterable[str | Path],
) -> IngestStats:
    """Persist immutable observations and hash-keyed canonical source records."""

    paths = [Path(path) for path in input_paths]
    before_observations = connection.execute(
        "SELECT COUNT(*) FROM raw_observations"
    ).fetchone()[0]
    before_records = connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]

    try:
        with connection:
            for path in paths:
                source_bytes = path.read_bytes()
                source_digest = hashlib.sha256(source_bytes).hexdigest()
                source_file = f"{path.name}:{source_digest}"
                try:
                    source_text = source_bytes.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"{path.name} is not valid UTF-8") from exc

                for line_number, line in enumerate(source_text.splitlines(), start=1):
                    if not line.strip():
                        continue
                    try:
                        decoded = json.loads(line)
                        record, canonical_json, record_hash = normalize_record(decoded)
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise ValueError(f"{path.name}:{line_number}: {exc}") from exc

                    connection.execute(
                        """
                        INSERT OR IGNORE INTO raw_records (
                            record_hash,
                            record_type,
                            business_key,
                            version,
                            event_time,
                            recorded_at,
                            payload_json,
                            canonical_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record_hash,
                            record["record_type"],
                            record["business_key"],
                            record["version"],
                            record["event_time"],
                            record["recorded_at"],
                            json.dumps(
                                record["payload"],
                                ensure_ascii=True,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            canonical_json,
                        ),
                    )
                    observation_material = (
                        f"{source_file}\n{line_number}\n{record_hash}".encode("utf-8")
                    )
                    observation_id = hashlib.sha256(observation_material).hexdigest()
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO raw_observations (
                            observation_id,
                            source_file,
                            source_line,
                            record_hash
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (observation_id, source_file, line_number, record_hash),
                    )
    except OSError as exc:
        raise ValueError(f"could not read source batch: {exc}") from exc

    after_observations = connection.execute(
        "SELECT COUNT(*) FROM raw_observations"
    ).fetchone()[0]
    after_records = connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]
    return IngestStats(
        files_seen=len(paths),
        observations_inserted=after_observations - before_observations,
        records_inserted=after_records - before_records,
    )


def rebuild_derived(connection: sqlite3.Connection) -> None:
    """Replace every staged and mart table from persistent canonical raw rows."""

    try:
        connection.executescript(_sql_text("derived.sql"))
    except sqlite3.Error:
        connection.rollback()
        raise


def _coerce_metric(value: float) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _summary_from_connection(
    connection: sqlite3.Connection,
    *,
    validate: bool,
) -> dict[str, Any]:
    result = {
        row[0]: _coerce_metric(row[1])
        for row in connection.execute(
            "SELECT metric_name, metric_value FROM mart_pipeline_health ORDER BY metric_name"
        )
    }
    switchback = connection.execute(
        """
        SELECT
            control_count,
            treatment_count,
            control_batched_rate,
            treatment_batched_rate,
            rate_difference
        FROM mart_switchback_analysis
        WHERE snapshot_key = 'all-terminal-outcomes'
        """
    ).fetchone()
    if switchback is not None:
        result["switchback"] = {
            "control_count": switchback[0],
            "treatment_count": switchback[1],
            "control_batched_rate": switchback[2],
            "treatment_batched_rate": switchback[3],
            "rate_difference": switchback[4],
        }

    if validate:
        from .contracts import assert_contracts

        checks = assert_contracts(connection)
        result["contracts_checked"] = len(checks)
        result["contract_failures"] = 0
    return result


def get_summary(
    database: sqlite3.Connection | str | Path,
    *,
    validate: bool = True,
) -> dict[str, Any]:
    """Return health and switchback metrics from a connection or database path."""

    if isinstance(database, sqlite3.Connection):
        return _summary_from_connection(database, validate=validate)
    connection = connect_database(database)
    try:
        initialize_database(connection)
        return _summary_from_connection(connection, validate=validate)
    finally:
        connection.close()


def run_pipeline(
    database_path: str | Path,
    input_paths: Iterable[str | Path],
    *,
    reset: bool = False,
) -> dict[str, Any]:
    """Ingest source batches, rebuild derived tables, and enforce contracts."""

    path = Path(database_path)
    if reset and path.exists():
        if not path.is_file():
            raise ValueError("database target exists and is not a file")
        path.unlink()

    connection = connect_database(path)
    try:
        initialize_database(connection)
        ingest_stats = ingest_jsonl(connection, input_paths)
        rebuild_derived(connection)
        result = _summary_from_connection(connection, validate=True)
        result["ingest"] = asdict(ingest_stats)
        return result
    finally:
        connection.close()
