# ATLAS 5.0 acceptance ledger

This release is in progress. ATLAS 4 remains the verified production baseline until the new remote commits and deployments are verified.
No independently validated city twin or observed municipal traffic benefit is claimed.
Historical benchmark artifacts and frozen source modules remain unchanged.

| Milestone | Current status | Evidence and remaining work |
| --- | --- | --- |
| A: five-city readiness | Fully verified within discovery scope | Input classifications, chronology, official-source follow-up and alternative corridors for all cities. Seattle resolves 23 current segments; London acquires 240 Whitehall hourly surveys. Historical lane/counter mapping remains unverified. |
| B: calibration | Partially implemented; independent twins blocked by missing data | Identifiability-gated weighted inversion and validation-selected arrival profiles; explicit held-out count errors and coverage. New Whitehall demand study fails its flow diagnostic. No independently validated simulation dynamics or field benefit. |
| C: integrated CV / ML | Partially implemented; transfer partly unsuccessful | Causal city forecasting, strict four-source transfer and proper interval scores; Calgary improves, Austin transfer worsens. Six complete CPU tracker repeats and confidence-aware compatible-source fusion implemented. City annotations, coeval calibrated sensor pairs, physical queues and verified directed graphs are missing. |
| D: robust optimization | Fully verified experiment; promotion experimentally unsuccessful | 150 development + 300 validation + 2,100 new final episodes across five cities, six cases and seven controllers. Decision-time portfolio frozen before final evaluation. Average benefit vs fixed/MP but loss vs original/cache and failed worst-episode guard; default unchanged. All 1,800 historical episodes preserved. |
| E: product / workers | Engineering workflow verified locally; public execution and human results unavailable | Connected calibration, real synchronized robustness replay and ten-seed pilot exports. Bounded authenticated durable native worker verified with actual SUMO; disabled publicly. Thirty desktop/mobile scans have zero automated violations; actual 36-second walkthrough and five screenshots are source-hashed. Human study protocol has zero participants. |
| F: release | In progress | 153 Python tests and 30 native browser tests pass. Lint/types/format, native/public builds, all evidence verifiers and fresh Docker CV/SUMO integration pass. Portfolio lint/types/build/media checks pass. Final public suite, remote CI and actual production verification remain. |

## First working increment

`docs/calibration-v5-protocol.json` fixes candidate shrinkage strengths, chronological
date partitions and acceptance thresholds before this increment's evaluation.
`scripts/evaluate_calibration_v5.py` reproduces `artifacts/cities/v5/calibration-readiness.json`
and the genuine observed-versus-estimated demand series. These estimates are **not
simulated counts**. The series explicitly leaves `simulated_count` null.

All input observations were already published or evaluated in ATLAS 4. The final
partition therefore represents chronological historical regression evidence,
**not a newly unseen ATLAS 5 cohort**. Data years are reported separately; an
estimated multi-year profile does not imply concurrent traffic observations.
Poisson exposure weighting is an assumption, not a measured sensor error model.

Five targeted tests verify identifiable weighted inversion, refusal of rank-deficient
or unverified mappings, chronological separation, absence of target leakage,
duplicate rejection, unknown-channel abstention, unit conversion and missing state metrics.

## Readiness findings

- Toronto: raw turning movements exist, but the nearest Bay/Queen network node's
  clustered topology does not directly correspond to the four survey approaches.
  Only 40% of historical final-period rows belong to channels seen in calibration.
- London: sparse Holborn observations lie outside the Whitehall corridor. Official
  DfT Whitehall point 27663 provides 240 actual direction/hour survey rows, acquired
  separately. Its historical demand estimate fails: 353.208 vehicles/hour MAE,
  68.83% normalized MAE and zero GEH below 5 across 48 final observations.
- Seattle: official study metadata provides the `compkey` street-segment join and
  direction-code definitions. The official current GIS joins 23 segments with no
  missing COMPKEYs; exact historic counter/lane placement still needs verification.
  Aggregate studies must not be double-counted.
- Austin: original camera counters are discontinued and independently unvalidated.
  The old linked study-area endpoint returns HTTP 404; the error is retained.
  Official Wavetronix radar counts/speeds and the current study-request register
  are alternative leads. A completed request is not itself a traffic observation.
- Calgary: permanent counts have actual official sensor coordinates. Signal records
  provide locations and device types, not timing plans. CalTRACS documents speed,
  classification and turning studies, whose report geometry and periods must align.

## Evidence levels

1. Exploratory simulation: current status of all five city twins.
2. Independently validated twin: requires held-out measured **simulation states and
   dynamics**, verified spatial correspondence and a documented scope. Count-profile
   fitting alone does not meet this criterion.
3. Observed field benefit: requires authorized operational evidence and a suitable
   causal evaluation. No ATLAS city currently meets this criterion.

Human usability results, city perception accuracy and field congestion savings
remain unmeasured. No participants, annotations, signal records or traffic savings
are invented to fill these gaps.

## Remaining acceptance boundaries

- **Blocked by missing data/authorization:** historical verified mappings, municipal
  timing/conflict/pedestrian plans, independent speed/travel-time/queue holdouts,
  coeval calibrated camera/detector pairs and agency-authorized field evaluation.
- **Experimentally unsuccessful:** Whitehall long-period demand reconstruction;
  Austin zero-shot transfer; portfolio worst-episode guard and overall comparison
  with cached/original MPC. Queue surrogate remains retired.
- **Not started because prerequisites are absent:** city directed-flow GNN,
  empirical multimodal contribution/queue ablations, genuine participant study and
  an agency-approved prospective pilot. No unsupported results are substituted.
- **Private native only:** new bounded paired execution. Kernel CPU/PID/disk limits,
  retention, TLS and reviewed hosting cost/security are prerequisites for public use.

See [generated results](atlas-5-results.md), [resume candidates](atlas-5-resume-bullets.md),
[execution architecture](execution-v5.md) and [usability protocol](usability-v5-protocol.md).
