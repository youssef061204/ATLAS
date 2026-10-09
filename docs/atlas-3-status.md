# ATLAS 3.0 acceptance ledger

Status describes the full requested criterion. An implemented primitive or positive benchmark does not imply commercial acceptance. All original twenty upgrades remain tracked in [the v2 ledger](atlas-2-status.md).

## Connected intelligence loop

**Partially complete.** Official observation → actual detection → versioned operator region → uncertain visible count → explicit demand assumptions → matched SUMO → actual metrics/vehicle replay → conditional explanation/pilot export executes on the native worker. Saved real outputs make the public path interactive. City demand, lane geometry, signal timing and forecast coverage are not independently calibrated. The evaluated highway GNN remains a separate domain; the city pipeline uses an unvalidated count prior. There is no field signal actuation, continuous five-city assimilation or validated camera-to-highway fusion.

## Computer vision

| ID | Criterion | Status and evidence | Remaining acceptance work |
|---|---|---|---|
| CV1 | Multi-class perception | Partial: real official snapshot detections; YOLO26n compared with unchanged YOLO11n on all 4,260 original annotated frames | Independent per-class five-city labels, emergency semantics and segmentation; candidate regresses aggregate mAP/recall |
| CV2 | Tracking and motion | Partial: continuous UA-DETRAC candidate tracking, IDF1/HOTA/ID switches; virtual-line crossing evaluator | Stronger tracking accuracy, validated physical motion, broader algorithms and cameras |
| CV3 | Lane scene understanding | Partial: versioned polygon correction on the actual new image; known-road validation; homography and held-out projection tests | Independently surveyed lane/stop-line/crosswalk accuracy and useful segmentation |
| CV4 | Visual queues | Partial: continuous calibrated-motion candidate separates stopped/slow/flowing tracks; snapshots refused | Annotated real queue-count and distance MAE; no measured queue accuracy claim |
| CV5 | Turning/flow | Partial: actual annotated crossing comparison, 18 predefined cases and all per-bin results | Surveyed turns/approaches and independent physical arrival validation |
| CV6 | Difficult conditions | Partial: 1,500 actual inferences on held-out real prefixes under five declared controlled degradations | Natural rain/snow/night/glare and camera-vibration holdouts; augmentation is not weather validation |
| CV7 | Camera/network alignment | Partial: point-to-polyline geolocation, operator road selection, exact-observation correction and distance guard | Camera heading/FOV/lane validation, directly observed versus inferred network coverage |
| CV8 | Anomaly perception | Partial: MAD temporal anomaly primitive and official road-event context with provenance | Labeled CV incident accuracy, temporal confirmation and calibrated false-alarm thresholds |
| CV9 | Edge perception | Partial: candidate stage accuracy/cost comparison and ROI-filtered inputs | Repeated isolated end-to-end cost/accuracy studies, adaptive scheduling, quantization or distillation benefits |
| CV10 | Visual fusion | Partial: count uncertainty, missing/stale tests, causal assimilation; mismatched historical counts explicitly separated | Compatible time-aligned detectors, disagreement/coverage calibration and validated city state |

## Machine learning

| ID | Criterion | Status and evidence | Remaining acceptance work |
|---|---|---|---|
| ML1 | Spatiotemporal GNN | Partial: trained 3,617-parameter directional network; beats matched MLP and original model at shared highway holdout; authorized trusted inference | Cross-network replication, repeated training seeds and intersection-domain forecasting |
| ML2 | Multimodal prediction | Partial: topology/time/calendar highway models; actual weather/incident ingestion kept separate | Valid time-aligned fusion with city camera/transit data and rolling independent city evaluation |
| ML3 | Probabilistic prediction | Partial: causal empirical intervals and measured undercoverage; controller assumes arrival envelopes | Calibrated city spillback/severe-congestion probabilities and proper probabilistic scores |
| ML4 | Constrained/offline RL | Not started: no RL result is represented as implemented | Train and evaluate a safety-gated candidate against strong unchanged comparators |
| ML5 | Cooperative learning | Not started for learned cooperation; deterministic graph coordination exists | Matched learned multi-agent comparison and measured communication/benefit tradeoff |
| ML6 | Learned simulator surrogate | Not started | Actual simulator training/holdout targets, error/OOD diagnostics and verified ranking speed/quality |
| ML7 | Self-supervised representation | Not started | Legitimate representation pretraining and controlled downstream benefit study |
| ML8 | Transfer/adaptation | Partial: seven modeled-network paired study, topology fallback and preserved Ingolstadt negative result | Learned few-shot/domain adaptation, calibrated OOD and consistent unseen-network gains |
| ML9 | Learning-guided control | Partial only for explicit forecasting/optimization separation; no learned policy warm-start claim | Actual learned candidate ranking/distillation evaluated through the deterministic gate |
| ML10 | Model health | Partial: pinned provenance/protocols, checksum-verified local loading, candidate regression tables and retained original defaults | Operational drift/calibration monitoring, shadow promotion and organizational rollback workflow |

**ML advancement criterion:** a meaningful evaluated highway forecasting improvement exists. The directional GNN reduces five-minute MAE from 2.4897 to 2.3441 mph and fifteen-minute MAE from 3.2143 to 2.9755 mph. The matched local MLP also improves the old model; graph messages add a separately measured benefit. Forward-only timing is not full HTTP latency. One training seed and shared historical holdout limit the claim; field city optimization improvement is not established.

## UX

| ID | Criterion | Status and implemented behavior | Remaining acceptance work |
|---|---|---|---|
| UX1 | Five-area architecture | Implemented; old routes retained under secondary navigation | Human validation of discoverability and 30-second comprehension |
| UX2 | Interactive cities | Partial: five catalogs, geographic maps, actual source checks, OSM corridors, reported road events and regional weather | Calibrated live congestion and complete feed freshness/uptime |
| UX3 | Camera intelligence | Partial: actual native image/boxes, counts and editable region; source changes clear unrelated evidence | Independently valid lanes/queues and permitted public image redistribution |
| UX4 | Guided experiments | Partial: explicit source, assumptions, authorization, matched controllers, progress and cancellation | Usability study and broader validated scenario presets |
| UX5 | Synchronized comparison | Implemented for recorded/new actual traces and new actual vehicle positions | Multimodal calibrated comparison and broader camera choices |
| UX6 | Performance dashboard | Partial: city/controller/seed, actual metrics, forecast and vision comparator tables, cohort CIs | Full scenario/demand/version drill-down and rigorous accessible chart alternatives |
| UX7 | Explanations | Partial: actual controller reasons, admissible alternatives, source uncertainty and conditional outcomes | Nontechnical comprehension and calibrated downstream risk explanations |
| UX8 | Loading/error states | Partial: explicit unavailable/empty source, zero-demand refusal, durable job states and bounded cancellation | Recovery/load testing under larger production workloads |
| UX9 | Speed/responsiveness | Partial: saved replay, lossless evidence compression, direct single-experiment loading; desktop and 390px interaction checks | Measured render/payload/bundle budgets, larger workload and device profiles |
| UX10 | Accessibility/product quality | Partial: named keyboard controls, corrected contrast, semantic map groups, desktop/mobile automated scans | Focus/manual accessibility review, broader device coverage and certification |
| UX11 | Shareable experiments | Implemented stable completed-result links, exact lineage/source/date/assumptions, export and clearly separate public replay | Public links for additional native-only records and broader version selection |
| UX12 | Real user testing | Partial: actual browser tasks and automated accessibility scans | Human task-completion/time/error studies, measured Lighthouse and Core Web Vitals; no fabricated usability result |

Automated accessibility scans and browser checks are engineering evidence, not WCAG certification or a human usability study. Production publication of this increment must be separately verified; the existing deployed ATLAS is not proof that these changes are live.
