# Data Contract

All timestamps are ISO 8601 UTC strings with a trailing `Z`. Monetary values
use integer minor units. Coordinates are unitless synthetic planar values.

## Record envelope

Every generated record contains:

| Field | Contract |
|---|---|
| `record_type` | One of `zone`, `switch_state`, `delivery_event`, `ledger_entry` |
| `business_key` | Stable key for version resolution |
| `version` | Positive integer; larger values supersede smaller values |
| `event_time` | When the represented business event occurred |
| `recorded_at` | When the source made the record visible |
| `payload` | Type-specific JSON object |

## Raw layer

### `raw_observations`

Grain: source batch + source line + canonical record hash. It answers how many
observations arrived and how many repeated an already-known record.

### `raw_records`

Grain: canonical SHA-256 record hash. It stores every distinct source version
once, independent of file replay.

## Staging layer

### `stg_delivery_events`

Grain: event business key after deterministic version resolution. Delivery
events include requests, dispatch attempts, accepted dispatches, revocations,
completions, and cancellations.

### `stg_ledger_entries`

Grain: monetary entry business key after version resolution. Entry types are
base, adjustment, and reversal. Values remain signed integers.

### `stg_switch_states`

Grain: service cell + effective time. The arm is reconstructed as of each
request rather than read from current state.

### `stg_zones`

Grain: fictional service-cell key. Bounds define rectangles on the demo grid.

## Mart layer

### `mart_delivery_outcomes`

Grain: delivery key.

- `request_time`: first canonical request event.
- `final_assignment_time`: latest canonical accepted dispatch event.
- `assignment_latency_seconds`: non-negative elapsed event time.
- `outcome`: `completed`, `cancelled`, or `open`.
- `switchback_arm`: most recent arm effective at request time.
- `is_batched`: terminal synthetic outcome flag where available.

### `mart_ledger_reconciliation`

Grain: delivery key. A cancelled delivery reconciles when signed net value is
zero. A completed delivery reconciles when no reversal is present and net value
equals base plus adjustments. Exceptions are retained as data-quality output.

### `mart_geospatial_quality`

Grain: delivery key. The mart checks whether the pickup lies inside its stated
service cell and whether squared pickup-to-dropoff distance remains within the
demo plausibility rule.

### `mart_switchback_analysis`

Grain: one analysis snapshot. It reports observation counts and batched rates
for control and treatment, plus their descriptive difference.

### `mart_pipeline_health`

Grain: metric name. Metrics cover observation volume, canonical volume,
duplicate observations, late records, outcome state, and detected ledger or
geospatial exceptions.

## Executable invariants

`urban_data_platform.contracts` verifies required columns, key uniqueness,
referential integrity, non-negative assignment latency, bounded rates, valid
quality flags, and agreement between staged rows and the winning raw version.
