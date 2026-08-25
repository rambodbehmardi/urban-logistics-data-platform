# Urban Logistics Data Platform

Operational analytics gets difficult when the same event can arrive twice, change
later, or mean something different under the policy that was active at event time. I
built this compact, runnable reference to make those problems inspectable without
exposing a production system.

The lab uses generated data and demonstrates deterministic event generation, idempotent ingestion,
version-aware staging, analytical marts, data-quality contracts, ledger
reconciliation, geospatial plausibility checks, and switchback analysis.

All records, entities, coordinates, policies, and monetary values in this
repository are synthetic. The implementation was written from a blank slate
and contains no production records, proprietary table designs, credentials,
customer identifiers, internal decision rules, or copied operational queries.

## What the demo proves

- Replaying the same files does not duplicate canonical raw records.
- Exact duplicate observations remain measurable without polluting staging.
- Event revisions resolve by version, record time, and a stable hash tie-break.
- The final accepted dispatch event is selected from event history.
- Late records update downstream outcomes on the next deterministic rebuild.
- Integer monetary entries reconcile adjustments and reversals without
  floating-point drift.
- Synthetic planar coordinates are checked against generated service cells.
- Switchback state is reconstructed at request time before outcomes are
  aggregated.

## Quick start

Requirements: Python 3.11 or newer and GNU Make.

```bash
make demo
make check
```

`make demo` writes generated artifacts under `build/`, runs the complete
pipeline, validates every contract, and prints a JSON summary. `make check`
runs bytecode compilation, unit and end-to-end tests, the demo, and the public
safety scan.

The package can also be run directly:

```bash
PYTHONPATH=src python3 -m urban_data_platform demo \
  --output-dir build/raw \
  --db build/platform.db \
  --reset
```

## Architecture

```text
deterministic JSONL generator
          |
          v
raw observations + canonical raw records
          |
          v
version-aware staging
          |
          +-------------------+--------------------+
          v                   v                    v
delivery outcomes       ledger checks       switchback state
          |                   |                    |
          +-------------------+--------------------+
                              |
                              v
                quality and metric contracts
```

Read [the architecture](docs/ARCHITECTURE.md), [the data contract](docs/DATA_CONTRACT.md),
[the public-safety policy](PUBLIC_SAFETY.md), [the limitations](LIMITATIONS.md),
[the workflow catalog](docs/WORKFLOW_CATALOG.md), and
[the compact case-study map](docs/case-studies/INDEX.md) for the design rationale.

## Repository layout

```text
src/urban_data_platform/   generator, ingestion, transforms, contracts, CLI
tests/                     deterministic and end-to-end checks
scripts/                   public-safety command
docs/                      architecture, contracts, and case-study map
.github/workflows/         reproducible CI
```

## License

The clean-room code and original documentation in this repository are
available under the MIT License. Generated demo records carry no real-world
meaning.
