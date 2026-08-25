# Workflow and Analysis Catalog

This catalog is my public account of the engineering patterns behind eighteen urban-
logistics analytics workstreams. It explains the question, data flow, guardrail, and
evidence boundary without publishing production SQL, schemas, identifiers, locations,
thresholds, schedules, financial values, or proprietary policy logic.

The runnable repository implements the shared foundations with generated data. The
catalog adds the part that code alone cannot show: why each pattern exists and what I
would need to verify before treating its output as a decision.

## Two recurring flows

### A governed operational update

```text
scheduled trigger
      |
      v
versioned state + configuration
      |
      v
schema and configuration validation
      |
      v
base population + independent controls
      |
      v
keyed merge + diff-only output
      |
      v
controlled bulk handoff
      |
      v
read-back / explicit success contract
      |
      +--> success report
      |
      +--> failure alert + hard stop
```

The important design choice is that a successful request is not accepted as proof of a
successful state change. The workflow verifies what was written and makes an empty or
ambiguous result fail visibly.

### A lineage-aware policy analysis

```text
raw event history
      |
      v
deduplication + revision resolution
      |
      v
policy state reconstructed at event time
      |
      v
final outcome + mature observation window
      |
      v
cohorts / uncertainty / heterogeneity
      |
      v
descriptive result or qualified causal estimate
```

Here the main risk is temporal leakage: using today's policy label for an event that
happened under an earlier state. The public pipeline demonstrates event-time state
reconstruction and keeps measured outcomes separate from causal interpretation.

## The eighteen workstreams

| # | Public theme | Engineering approach | Evidence and decision boundary |
| ---: | --- | --- | --- |
| 1 | **Area-shift policy impact** | Build an effective-dated area-time panel, reconstruct the active state, and join only outcomes mature enough to observe. | Report descriptive movement first; claim causality only with a defensible comparison and uncertainty. |
| 2 | **Dispatch acceptance monitoring** | Preserve every attempt, select the final accepted state from event history, and define request-, attempt-, and courier-level grains separately. | Never mix denominators or treat missing terminal events as rejection without an explicit rule. |
| 3 | **Dispatch-radius automation** | Validate versioned configuration, compute scoped changes, emit only differences, perform a controlled handoff, and verify the written state. | A validated implementation pattern does not imply that every proposed branch was deployed. |
| 4 | **Revocation and restriction analysis** | Audit deterministic assignment, candidate filtering, deduplication, insertion/report branches, and downstream exposure before estimating outcomes. | Mechanism fidelity can be proven while business impact remains statistically inconclusive. |
| 5 | **Delay-tier audit** | Reconstruct the effective rule at event time and test boundary conditions with integer-safe comparisons. | A correct rule evaluation does not establish that the policy itself is optimal. |
| 6 | **Weekly cancellation diagnostics** | Resolve terminal events, normalize complete time windows, segment by stable dimensions, and reconcile totals before root-cause drill-down. | Partial periods and changing population mix are labelled rather than silently compared. |
| 7 | **Distance-policy validation** | Recompute distance from generated coordinates, compare event-time policy states, and inspect sensitivity around boundary cases. | Distance associations are not presented as causal service effects without a valid design. |
| 8 | **Hold-and-batch switchback evaluation** | Reconstruct treatment from event-time state, track lineage to final outcomes, estimate uncertainty, and inspect heterogeneous effects. | Treatment execution, exposure, and outcome evidence are reported as separate questions. |
| 9 | **Geospatial risk plausibility** | Validate coordinate ranges, service-cell membership, radial distance, and impossible spatial combinations before analysis. | The public lab uses a fictional grid and makes no claim about a real location or actor. |
| 10 | **Regional dispatch root-cause analysis** | Decompose the funnel by stable zone-like dimensions, attempt history, terminal state, and maturity-aware cohorts. | A regional pattern is a diagnostic lead, not proof that geography caused the outcome. |
| 11 | **Service-quality cohort analysis** | Define cohort entry once, wait for the full outcome horizon, and compare like-for-like denominators with confidence intervals. | Immature cohorts are excluded or labelled; they are never counted as failures by convenience. |
| 12 | **Courier-recovery reporting** | Materialize a reproducible reporting mart from canonical events and expose metric definitions alongside the reporting layer. | The dashboard is a consumer of governed metrics, not the place where business logic is hidden. |
| 13 | **Fulfilment root-cause audit** | Trace source-to-final-event lineage, quantify duplicates and missing states, and separate data loss from operational loss. | Data-pipeline defects are repaired before interpreting an operational rate. |
| 14 | **Fulfilment control surface** | Publish metric grain, numerator, denominator, exclusions, maturity rule, and reconciliation checks as a contract. | A control surface explains the measure; it does not manufacture an uplift claim. |
| 15 | **Margin and fulfilment decision control** | Keep ledger economics separate from event rates, validate state/configuration, update only controlled fields, read back, and report. | Financial signs and reversals must reconcile; stale outputs are not reused as current evidence. |
| 16 | **Shift-mode and allocation audit** | Reconstruct mode intervals, allocation state, reservations, and observed outcomes on complete windows. | Allocation and outcome association remains descriptive unless assignment conditions support inference. |
| 17 | **Compensation-ledger analysis** | Model base entries, adjustments, reversals, and final effective amounts with integer arithmetic and invariant checks. | No financial result is accepted until components reconcile at the declared grain. |
| 18 | **Utilisation and return analysis** | Build area-time panels, standardize exposure windows, and compare rates with explicit population and time denominators. | Composition effects, seasonality, and incomplete follow-up remain visible limitations. |

## What is executable here

The clean-room vertical slice implements the foundations shared by these workstreams:

- immutable observations and measurable duplicates;
- deterministic version resolution and replay safety;
- final-event selection from history;
- late-arriving revision handling;
- effective-time switchback state;
- generated geospatial checks;
- integer ledger components and reversals;
- analytical marts and executable metric contracts; and
- a public-safety scan that fails the release on unsafe content.

The repository does not claim that one compact schema reproduces eighteen production
systems. It gives reviewers one inspectable implementation of the engineering decisions
that recur across them.
