BEGIN IMMEDIATE;

DELETE FROM mart_pipeline_health;
DELETE FROM mart_switchback_analysis;
DELETE FROM mart_geospatial_quality;
DELETE FROM mart_ledger_reconciliation;
DELETE FROM mart_delivery_outcomes;
DELETE FROM stg_ledger_entries;
DELETE FROM stg_delivery_events;
DELETE FROM stg_switch_states;
DELETE FROM stg_zones;

WITH ranked AS (
    SELECT
        raw_records.*,
        ROW_NUMBER() OVER (
            PARTITION BY record_type, business_key
            ORDER BY version DESC, recorded_at DESC, record_hash DESC
        ) AS winner_rank
    FROM raw_records
    WHERE record_type = 'zone'
)
INSERT INTO stg_zones (
    business_key,
    zone_id,
    x_min,
    x_max,
    y_min,
    y_max,
    max_distance_squared,
    event_time,
    recorded_at,
    version,
    record_hash
)
SELECT
    business_key,
    json_extract(payload_json, '$.zone_id'),
    CAST(json_extract(payload_json, '$.x_min') AS REAL),
    CAST(json_extract(payload_json, '$.x_max') AS REAL),
    CAST(json_extract(payload_json, '$.y_min') AS REAL),
    CAST(json_extract(payload_json, '$.y_max') AS REAL),
    CAST(json_extract(payload_json, '$.max_distance_squared') AS REAL),
    event_time,
    recorded_at,
    version,
    record_hash
FROM ranked
WHERE winner_rank = 1;

WITH ranked AS (
    SELECT
        raw_records.*,
        ROW_NUMBER() OVER (
            PARTITION BY record_type, business_key
            ORDER BY version DESC, recorded_at DESC, record_hash DESC
        ) AS winner_rank
    FROM raw_records
    WHERE record_type = 'switch_state'
)
INSERT INTO stg_switch_states (
    business_key,
    zone_id,
    effective_at,
    arm,
    event_time,
    recorded_at,
    version,
    record_hash
)
SELECT
    business_key,
    json_extract(payload_json, '$.zone_id'),
    json_extract(payload_json, '$.effective_at'),
    json_extract(payload_json, '$.arm'),
    event_time,
    recorded_at,
    version,
    record_hash
FROM ranked
WHERE winner_rank = 1;

WITH ranked AS (
    SELECT
        raw_records.*,
        ROW_NUMBER() OVER (
            PARTITION BY record_type, business_key
            ORDER BY version DESC, recorded_at DESC, record_hash DESC
        ) AS winner_rank
    FROM raw_records
    WHERE record_type = 'delivery_event'
)
INSERT INTO stg_delivery_events (
    business_key,
    delivery_id,
    event_kind,
    zone_id,
    pickup_x,
    pickup_y,
    dropoff_x,
    dropoff_y,
    is_batched,
    event_time,
    recorded_at,
    version,
    record_hash
)
SELECT
    business_key,
    json_extract(payload_json, '$.delivery_id'),
    json_extract(payload_json, '$.event_kind'),
    json_extract(payload_json, '$.zone_id'),
    CAST(json_extract(payload_json, '$.pickup_x') AS REAL),
    CAST(json_extract(payload_json, '$.pickup_y') AS REAL),
    CAST(json_extract(payload_json, '$.dropoff_x') AS REAL),
    CAST(json_extract(payload_json, '$.dropoff_y') AS REAL),
    CAST(json_extract(payload_json, '$.is_batched') AS INTEGER),
    event_time,
    recorded_at,
    version,
    record_hash
FROM ranked
WHERE winner_rank = 1;

WITH ranked AS (
    SELECT
        raw_records.*,
        ROW_NUMBER() OVER (
            PARTITION BY record_type, business_key
            ORDER BY version DESC, recorded_at DESC, record_hash DESC
        ) AS winner_rank
    FROM raw_records
    WHERE record_type = 'ledger_entry'
)
INSERT INTO stg_ledger_entries (
    business_key,
    delivery_id,
    entry_type,
    amount_minor,
    reference_entry_key,
    event_time,
    recorded_at,
    version,
    record_hash
)
SELECT
    business_key,
    json_extract(payload_json, '$.delivery_id'),
    json_extract(payload_json, '$.entry_type'),
    CAST(json_extract(payload_json, '$.amount_minor') AS INTEGER),
    json_extract(payload_json, '$.reference_entry_key'),
    event_time,
    recorded_at,
    version,
    record_hash
FROM ranked
WHERE winner_rank = 1;

WITH requests AS (
    SELECT
        stg_delivery_events.*,
        ROW_NUMBER() OVER (
            PARTITION BY delivery_id
            ORDER BY event_time ASC, recorded_at ASC, business_key ASC
        ) AS event_rank
    FROM stg_delivery_events
    WHERE event_kind = 'requested'
),
accepted AS (
    SELECT
        stg_delivery_events.*,
        ROW_NUMBER() OVER (
            PARTITION BY delivery_id
            ORDER BY event_time DESC, recorded_at DESC, business_key DESC
        ) AS event_rank
    FROM stg_delivery_events
    WHERE event_kind = 'dispatch_accepted'
),
terminal AS (
    SELECT
        stg_delivery_events.*,
        ROW_NUMBER() OVER (
            PARTITION BY delivery_id
            ORDER BY event_time DESC, recorded_at DESC, business_key DESC
        ) AS event_rank
    FROM stg_delivery_events
    WHERE event_kind IN ('completed', 'cancelled')
)
INSERT INTO mart_delivery_outcomes (
    delivery_id,
    zone_id,
    request_event_key,
    request_time,
    final_assignment_key,
    final_assignment_time,
    assignment_latency_seconds,
    terminal_event_key,
    terminal_time,
    outcome,
    switchback_arm,
    is_batched
)
SELECT
    request.delivery_id,
    request.zone_id,
    request.business_key,
    request.event_time,
    assignment.business_key,
    assignment.event_time,
    CASE
        WHEN assignment.event_time IS NULL THEN NULL
        ELSE CAST(
            ROUND((julianday(assignment.event_time) - julianday(request.event_time)) * 86400.0)
            AS INTEGER
        )
    END,
    terminal_event.business_key,
    terminal_event.event_time,
    COALESCE(terminal_event.event_kind, 'open'),
    (
        SELECT switch_state.arm
        FROM stg_switch_states AS switch_state
        WHERE switch_state.zone_id = request.zone_id
          AND switch_state.effective_at <= request.event_time
        ORDER BY switch_state.effective_at DESC, switch_state.business_key DESC
        LIMIT 1
    ),
    terminal_event.is_batched
FROM requests AS request
LEFT JOIN accepted AS assignment
    ON assignment.delivery_id = request.delivery_id
   AND assignment.event_rank = 1
LEFT JOIN terminal AS terminal_event
    ON terminal_event.delivery_id = request.delivery_id
   AND terminal_event.event_rank = 1
WHERE request.event_rank = 1;

WITH ledger AS (
    SELECT
        delivery_id,
        COUNT(*) AS entry_count,
        SUM(CASE WHEN entry_type = 'base' THEN 1 ELSE 0 END) AS base_entry_count,
        SUM(CASE WHEN entry_type = 'reversal' THEN 1 ELSE 0 END) AS reversal_entry_count,
        SUM(CASE WHEN entry_type = 'base' THEN amount_minor ELSE 0 END) AS base_minor,
        SUM(CASE WHEN entry_type = 'adjustment' THEN amount_minor ELSE 0 END) AS adjustment_minor,
        SUM(CASE WHEN entry_type = 'reversal' THEN amount_minor ELSE 0 END) AS reversal_minor,
        SUM(amount_minor) AS net_minor
    FROM stg_ledger_entries
    GROUP BY delivery_id
),
evaluated AS (
    SELECT
        outcome.delivery_id,
        outcome.outcome,
        COALESCE(ledger.entry_count, 0) AS entry_count,
        COALESCE(ledger.base_entry_count, 0) AS base_entry_count,
        COALESCE(ledger.reversal_entry_count, 0) AS reversal_entry_count,
        COALESCE(ledger.base_minor, 0) AS base_minor,
        COALESCE(ledger.adjustment_minor, 0) AS adjustment_minor,
        COALESCE(ledger.reversal_minor, 0) AS reversal_minor,
        COALESCE(ledger.net_minor, 0) AS net_minor,
        CASE
            WHEN outcome.outcome = 'open' THEN 1
            WHEN outcome.outcome = 'completed'
              AND COALESCE(ledger.base_entry_count, 0) = 1
              AND COALESCE(ledger.reversal_entry_count, 0) = 0
              AND COALESCE(ledger.net_minor, 0) =
                  COALESCE(ledger.base_minor, 0) + COALESCE(ledger.adjustment_minor, 0)
                THEN 1
            WHEN outcome.outcome = 'cancelled'
              AND COALESCE(ledger.base_entry_count, 0) = 1
              AND COALESCE(ledger.reversal_entry_count, 0) >= 1
              AND COALESCE(ledger.net_minor, 0) = 0
                THEN 1
            ELSE 0
        END AS is_reconciled
    FROM mart_delivery_outcomes AS outcome
    LEFT JOIN ledger ON ledger.delivery_id = outcome.delivery_id
)
INSERT INTO mart_ledger_reconciliation (
    delivery_id,
    outcome,
    entry_count,
    base_entry_count,
    reversal_entry_count,
    base_minor,
    adjustment_minor,
    reversal_minor,
    net_minor,
    reconciliation_status,
    is_reconciled
)
SELECT
    delivery_id,
    outcome,
    entry_count,
    base_entry_count,
    reversal_entry_count,
    base_minor,
    adjustment_minor,
    reversal_minor,
    net_minor,
    CASE
        WHEN outcome = 'open' THEN 'not_due'
        WHEN is_reconciled = 1 THEN 'passed'
        ELSE 'exception'
    END,
    is_reconciled
FROM evaluated;

WITH checks AS (
    SELECT
        outcome.delivery_id,
        outcome.zone_id,
        request.pickup_x,
        request.pickup_y,
        request.dropoff_x,
        request.dropoff_y,
        zone.x_min,
        zone.x_max,
        zone.y_min,
        zone.y_max,
        zone.max_distance_squared,
        (request.dropoff_x - request.pickup_x) * (request.dropoff_x - request.pickup_x)
            + (request.dropoff_y - request.pickup_y) * (request.dropoff_y - request.pickup_y)
            AS distance_squared
    FROM mart_delivery_outcomes AS outcome
    JOIN stg_delivery_events AS request
      ON request.business_key = outcome.request_event_key
    LEFT JOIN stg_zones AS zone
      ON zone.zone_id = outcome.zone_id
)
INSERT INTO mart_geospatial_quality (
    delivery_id,
    zone_id,
    pickup_in_zone,
    distance_squared,
    distance_plausible,
    is_valid
)
SELECT
    delivery_id,
    zone_id,
    CASE
        WHEN pickup_x BETWEEN x_min AND x_max
         AND pickup_y BETWEEN y_min AND y_max THEN 1
        ELSE 0
    END,
    distance_squared,
    CASE
        WHEN distance_squared <= max_distance_squared THEN 1
        ELSE 0
    END,
    CASE
        WHEN pickup_x BETWEEN x_min AND x_max
         AND pickup_y BETWEEN y_min AND y_max
         AND distance_squared <= max_distance_squared THEN 1
        ELSE 0
    END
FROM checks;

WITH eligible AS (
    SELECT switchback_arm, is_batched
    FROM mart_delivery_outcomes
    WHERE outcome IN ('completed', 'cancelled')
      AND switchback_arm IN ('control', 'treatment')
      AND is_batched IN (0, 1)
),
aggregated AS (
    SELECT
        SUM(CASE WHEN switchback_arm = 'control' THEN 1 ELSE 0 END) AS control_count,
        SUM(CASE WHEN switchback_arm = 'treatment' THEN 1 ELSE 0 END) AS treatment_count,
        COALESCE(
            1.0 * SUM(CASE WHEN switchback_arm = 'control' THEN is_batched ELSE 0 END)
                / NULLIF(SUM(CASE WHEN switchback_arm = 'control' THEN 1 ELSE 0 END), 0),
            0.0
        ) AS control_rate,
        COALESCE(
            1.0 * SUM(CASE WHEN switchback_arm = 'treatment' THEN is_batched ELSE 0 END)
                / NULLIF(SUM(CASE WHEN switchback_arm = 'treatment' THEN 1 ELSE 0 END), 0),
            0.0
        ) AS treatment_rate
    FROM eligible
)
INSERT INTO mart_switchback_analysis (
    snapshot_key,
    control_count,
    treatment_count,
    control_batched_rate,
    treatment_batched_rate,
    rate_difference
)
SELECT
    'all-terminal-outcomes',
    COALESCE(control_count, 0),
    COALESCE(treatment_count, 0),
    control_rate,
    treatment_rate,
    treatment_rate - control_rate
FROM aggregated;

INSERT INTO mart_pipeline_health (metric_name, metric_value)
SELECT 'raw_observations', COUNT(*) FROM raw_observations
UNION ALL
SELECT 'raw_records', COUNT(*) FROM raw_records
UNION ALL
SELECT 'duplicate_observations', COUNT(*) - COUNT(DISTINCT record_hash) FROM raw_observations
UNION ALL
SELECT
    'late_records',
    COUNT(*)
FROM raw_records
WHERE (julianday(recorded_at) - julianday(event_time)) * 86400.0 > 300.0
UNION ALL
SELECT 'open_outcomes', COUNT(*) FROM mart_delivery_outcomes WHERE outcome = 'open'
UNION ALL
SELECT
    'terminal_outcomes',
    COUNT(*)
FROM mart_delivery_outcomes
WHERE outcome IN ('completed', 'cancelled')
UNION ALL
SELECT
    'ledger_exceptions',
    COUNT(*)
FROM mart_ledger_reconciliation
WHERE reconciliation_status = 'exception'
UNION ALL
SELECT 'geo_exceptions', COUNT(*) FROM mart_geospatial_quality WHERE is_valid = 0
UNION ALL
SELECT
    'corrected_business_keys',
    COUNT(*)
FROM (
    SELECT record_type, business_key
    FROM raw_records
    GROUP BY record_type, business_key
    HAVING MAX(version) > 1
);

COMMIT;
