PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_records (
    record_hash TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    business_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    event_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    CHECK (record_type IN ('zone', 'switch_state', 'delivery_event', 'ledger_entry'))
);

CREATE INDEX IF NOT EXISTS idx_raw_records_business_key
    ON raw_records (record_type, business_key, version, recorded_at);

CREATE TABLE IF NOT EXISTS raw_observations (
    observation_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_line INTEGER NOT NULL CHECK (source_line > 0),
    record_hash TEXT NOT NULL REFERENCES raw_records (record_hash),
    UNIQUE (source_file, source_line, record_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_observations_record_hash
    ON raw_observations (record_hash);

CREATE TABLE IF NOT EXISTS stg_zones (
    business_key TEXT NOT NULL UNIQUE,
    zone_id TEXT PRIMARY KEY,
    x_min REAL NOT NULL,
    x_max REAL NOT NULL,
    y_min REAL NOT NULL,
    y_max REAL NOT NULL,
    max_distance_squared REAL NOT NULL,
    event_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    record_hash TEXT NOT NULL REFERENCES raw_records (record_hash),
    CHECK (x_min < x_max),
    CHECK (y_min < y_max),
    CHECK (max_distance_squared > 0)
);

CREATE TABLE IF NOT EXISTS stg_switch_states (
    business_key TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    arm TEXT NOT NULL CHECK (arm IN ('control', 'treatment')),
    event_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    record_hash TEXT NOT NULL REFERENCES raw_records (record_hash),
    UNIQUE (zone_id, effective_at)
);

CREATE INDEX IF NOT EXISTS idx_switch_state_lookup
    ON stg_switch_states (zone_id, effective_at DESC);

CREATE TABLE IF NOT EXISTS stg_delivery_events (
    business_key TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    zone_id TEXT,
    pickup_x REAL,
    pickup_y REAL,
    dropoff_x REAL,
    dropoff_y REAL,
    is_batched INTEGER CHECK (is_batched IN (0, 1) OR is_batched IS NULL),
    event_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    record_hash TEXT NOT NULL REFERENCES raw_records (record_hash),
    CHECK (
        event_kind IN (
            'requested',
            'dispatch_attempt',
            'dispatch_accepted',
            'dispatch_revoked',
            'completed',
            'cancelled'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_delivery_event_timeline
    ON stg_delivery_events (delivery_id, event_time, business_key);

CREATE TABLE IF NOT EXISTS stg_ledger_entries (
    business_key TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('base', 'adjustment', 'reversal')),
    amount_minor INTEGER NOT NULL,
    reference_entry_key TEXT,
    event_time TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    record_hash TEXT NOT NULL REFERENCES raw_records (record_hash)
);

CREATE INDEX IF NOT EXISTS idx_ledger_delivery
    ON stg_ledger_entries (delivery_id, entry_type);

CREATE TABLE IF NOT EXISTS mart_delivery_outcomes (
    delivery_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    request_event_key TEXT NOT NULL,
    request_time TEXT NOT NULL,
    final_assignment_key TEXT,
    final_assignment_time TEXT,
    assignment_latency_seconds INTEGER CHECK (
        assignment_latency_seconds >= 0 OR assignment_latency_seconds IS NULL
    ),
    terminal_event_key TEXT,
    terminal_time TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('completed', 'cancelled', 'open')),
    switchback_arm TEXT CHECK (
        switchback_arm IN ('control', 'treatment') OR switchback_arm IS NULL
    ),
    is_batched INTEGER CHECK (is_batched IN (0, 1) OR is_batched IS NULL)
);

CREATE TABLE IF NOT EXISTS mart_ledger_reconciliation (
    delivery_id TEXT PRIMARY KEY REFERENCES mart_delivery_outcomes (delivery_id),
    outcome TEXT NOT NULL,
    entry_count INTEGER NOT NULL,
    base_entry_count INTEGER NOT NULL,
    reversal_entry_count INTEGER NOT NULL,
    base_minor INTEGER NOT NULL,
    adjustment_minor INTEGER NOT NULL,
    reversal_minor INTEGER NOT NULL,
    net_minor INTEGER NOT NULL,
    reconciliation_status TEXT NOT NULL CHECK (
        reconciliation_status IN ('passed', 'exception', 'not_due')
    ),
    is_reconciled INTEGER NOT NULL CHECK (is_reconciled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS mart_geospatial_quality (
    delivery_id TEXT PRIMARY KEY REFERENCES mart_delivery_outcomes (delivery_id),
    zone_id TEXT NOT NULL,
    pickup_in_zone INTEGER NOT NULL CHECK (pickup_in_zone IN (0, 1)),
    distance_squared REAL,
    distance_plausible INTEGER NOT NULL CHECK (distance_plausible IN (0, 1)),
    is_valid INTEGER NOT NULL CHECK (is_valid IN (0, 1))
);

CREATE TABLE IF NOT EXISTS mart_switchback_analysis (
    snapshot_key TEXT PRIMARY KEY,
    control_count INTEGER NOT NULL,
    treatment_count INTEGER NOT NULL,
    control_batched_rate REAL NOT NULL,
    treatment_batched_rate REAL NOT NULL,
    rate_difference REAL NOT NULL,
    CHECK (control_batched_rate BETWEEN 0.0 AND 1.0),
    CHECK (treatment_batched_rate BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS mart_pipeline_health (
    metric_name TEXT PRIMARY KEY,
    metric_value REAL NOT NULL
);
