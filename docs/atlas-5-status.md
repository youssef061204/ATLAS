# ATLAS 5.0 acceptance ledger

This release is in progress. ATLAS 4 remains the verified production baseline.
No independently validated city twin or observed municipal traffic benefit is claimed.
Historical benchmark artifacts and frozen source modules remain unchanged.

| Milestone | Current status | Evidence and remaining work |
| --- | --- | --- |
| A: five-city readiness | Partially implemented | Automated input classifications, chronology, official-source discovery and alternative corridor candidates for all five cities. Historical sensor-to-road mappings remain unverified. |
| B: calibration | Partially implemented | Identifiability-gated nonnegative weighted least squares; exposure-weighted arrival profiles selected on validation dates; separate historical regression evaluation and date-cluster uncertainty. Independent simulation-state validation remains blocked by missing mapped state observations. |
| C: integrated CV / ML | Not started | Preserve production ByteTrack and highway GNN. New city annotations, contemporaneous detector/camera pairs and queue labels are unavailable. Forecast transfer and integration work remains. |
| D: robust optimization | Not started | Preserve all 1,800 historical episodes, controller regressions and safety evidence. New decision-time policy and separate final-seed protocol remain. |
| E: product / workers | Not started | Existing five-city UI, genuine public replay and authenticated native processing stay operational. Calibration dashboard, bounded worker architecture and new usability protocol remain. |
| F: release | Not started | Incremental calibration tests pass; full release verification, new resume evidence, portfolio changes, remote commits and production browser verification remain. |

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
  DfT metadata identifies Whitehall count point 27663 on A3212; investigate its
  actual hourly survey counts instead of using annual estimated flows as truth.
- Seattle: official study metadata provides the `compkey` street-segment join and
  direction-code definitions. Geometry and historical direction matching remain
  prerequisites for network calibration. Aggregate studies must not be double-counted.
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
