# Limitations

- SQLite is used for a fast local demonstration. The project does not model
  distributed ingestion, replication, workload isolation, or cluster tuning.
- JSONL files stand in for a durable event bus and object storage.
- Rebuilding staging and marts is intentionally simple. A larger system would
  use incremental partitions, checkpoints, backfills, and an orchestrator.
- The generated planar grid is not a road network or geographic coordinate
  reference system. The plausibility mart demonstrates validation mechanics,
  not route planning.
- The switchback output is descriptive. It does not by itself establish a
  causal effect, address interference, or replace a pre-registered analysis.
- Ledger rules cover base entries, adjustments, and reversals only. They are
  not an accounting standard.
- The safety scan uses patterns and cannot detect every form of confidential
  context. Manual review remains mandatory.
- This repository demonstrates engineering patterns with synthetic data; it
  makes no claim that the demo stack was deployed in a live environment.
