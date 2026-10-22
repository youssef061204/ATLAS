# ATLAS 8 physical-twin diagnosis (development evidence)

**Status: physical twin not accepted.** This is a reproducible root-cause investigation, not an ATLAS 8 validation result or a new controller claim. The ATLAS 7 [frozen protocol](reality-v7-protocol.json), [results](reality-v7-results.md), real-video replay, and controller evidence remain intact. All analyses here use the already inspected Lankershim first recording. The 0–300 s window is development; 600–1,000 s is a **known regression cohort**, not a fresh holdout. The weak 1,020–1,120 s tail and CityFlow S03 labels have already been opened in ATLAS 7 and cannot be recycled as independent tests.

## What the video-driven system actually measures

ATLAS 7 processed all 11,220 consecutive frames of FHWA Lankershim camera 4, showed CV boxes and trajectories synchronized with a native free-running SUMO reconstruction, and exposed the failed physical gate. On the unchanged 2,670-state, 600–1,000 s cohort, its CV point IDF1 was **0.7259**, reference match coverage **65.8%**, and visible-count MAE **1.878 vehicles**. SUMO represented only **54.6%** of those reference states, placed **12.7%** within 4 m, and had **13.64 m** uncapped position MAE among present states. These are spatial point/vehicle-state measures, not a traffic-light intervention or an accepted digital twin.

The second official Lankershim camera-3 recording was also acquired as a complete, CRC- and SHA-verified 449 MB archive member. The [full-video integrity audit](../artifacts/reality/v8/lankershim-camera3-video-integrity.json) decoded all **11,220 frames at 10 FPS**. All **11,219 consecutive frame pairs changed** and none was an exact duplicate. This is continuous moving footage, not a still-image feed. Sampled camera-3 views overlap the camera-4 corridor, but they did not establish a readable Main Street lamp color; no signal-state validation is inferred from this acquisition. The raw recording remains Git-ignored.

The [lifecycle audit](../artifacts/reality/v8/lifecycle-known-regression.json) partitions the same 2,670 reference states without dropping unmatched vehicles:

| Mutually exclusive stage | States | Practical meaning |
|---|---:|---|
| No CV-birth association | 297 | No confident one-time reference/CV correspondence |
| Before associated CV birth | 357 | Reference vehicle was visible before its CV-derived admission |
| Before first sampled native state | 177 | Admission happened late or native output had not appeared at 1 Hz |
| After last sampled native state | 382 | Native track exited before the remaining observed states |
| Native present, farther than 4 m | 1,119 | Corresponded, but physically misplaced |
| Native present, within 4 m | 338 | Meets the spatial gate at that second |

The 1 Hz native samples cannot by themselves establish exact insertion and exit timestamps. One-time spatial birth association may be wrong, and same-second CV spatial matches are not verified identities. The per-vehicle diagnostic remains ignored locally; the published artifact contains aggregate counts and hashes.

## Controlled demand ablation

In [0–300 s development](../artifacts/reality/v8/demand-attribution-development.json), both runs use **exactly the same** Main Street network, approximate signal program, SUMO behavior and random seed. The reference-initialized run supplies the first independently annotated vehicle pose, speed and length **at its observation time**. It does not correct any later state. Its reference identities and starts make it an **oracle diagnostic**, not deployable CV performance or independent predictive accuracy.

| Same 1,441 scoring states, 30–300 s | CV-driven births | Reference first-state births |
|---|---:|---:|
| Native presence | 69.47% | 93.41% |
| Within 4 m, all reference states | 18.74% | 19.64% |
| Uncapped position MAE among present states | 11.75 m | 16.14 m |
| Visible-count MAE | 1.478 | 1.333 |

The first-state intervention recovers presence but **does not recover accurate motion**. The oracle's larger position error is not a fair deployable model comparison: it changes the set of native/reference pairs, including difficult states that the CV run missed. Read coverage and position error together.

The direction split exposed a much sharper failure. In the original reference-initialized run, northbound states after the modeled Main Street junction have **33.58 m** position MAE and just **1.34%** within 4 m, versus southbound **10.47 m** and **26.05%**. In a separate [post-Main oracle ablation](../artifacts/reality/v8/post-main-admission-ablation-development.json), the first annotated northbound state is moved to the outgoing edge just *after* that junction; southbound admissions and the entire network, signal program, driver model, seed and safety checks remain unchanged. All **1,441** reference scoring states are still evaluated, and the paired northbound cohort contains the same **374 states** in both runs.

| Identical post-birth development cohort | Original oracle birth before Main | Oracle birth after Main |
|---|---:|---:|
| Northbound native presence | 88.24% | 97.86% |
| Northbound within 4 m | 1.34% | 32.62% |
| Northbound position MAE, present pairs | 33.58 m | 6.56 m |
| All-direction within 4 m | 19.64% | 27.76% |
| All-direction position MAE, present pairs | 16.14 m | 9.43 m |
| Southbound position MAE | 10.47 m | 10.47 m |

This **localizes a large part of error to entering/crossing Main Street**. It does not identify whether the precise cause is signal phase, insertion, approach geometry or interactions among them. It uses an oracle state later in time and bypasses the intersection, so it cannot be advertised as an improved operational model, a fixed signal controller, or accepted physical prediction. Even the bypassed northbound 4 m coverage is only 32.62%.

A separate [approach-length ablation](../artifacts/reality/v8/south-approach-length-ablation-development.json) tests a more specific structural hypothesis: the original southbound-side incoming edge is just **15.49 m** long, leaving little modeled space for northbound approach behavior. Extending it to **95.49 m** while preserving each original first-state position to within **0.10 m**, the exact controlled lane connections, signal sequence, vehicle settings and seed raises native presence **93.41% to 96.04%** but **worsens** position MAE **16.14 to 17.52 m**; within-4-m coverage changes only **19.64% to 19.99%**. The added remote geometry is estimated. Merely adding approach length does not fix the crossing dynamics. A repeat native run produced identical timestep state XML; only SUMO's generation timestamp changed the compressed-file hash.

The independent trajectory [through-crossing audit](../artifacts/reality/v8/main-through-crossing-development.json) corroborates the direction asymmetry without using a tuned car-following parameter. For FHWA-labeled through movements crossing the current model's local-y 1,045 ft section, the first 1 Hz native outgoing-edge sample occurs a median **2.95 s after** observed passage northbound (68 pairs), versus **0.35 s after** southbound (158 pairs). This section is an estimated model junction, not a surveyed stop line; native sampling and internal-junction travel contribute to both differences. Some native vehicles cross earlier than observed, so a single global clock shift is not justified.

The [signed-residual audit](../artifacts/reality/v8/physical-residual-development.json) projects native minus observed center displacement onto the direction of travel and its lateral normal. On the known 600–1,000 s CV cohort, the 90th percentile of **absolute along-road error is 31.59 m**, while the lateral counterpart is **4.33 m**. For the 30–300 s CV run, those figures are **28.04 m** and **3.62 m**. Mean signed longitudinal error on the known cohort is only **+1.28 m** despite a **13.64 m** radial MAE: some vehicles run far ahead and others far behind. The dominant issue is dynamic timing/movement, not a single common translational offset. These errors are conditional on matched, present native states; the unconditional denominator above still applies.

## Road and route evidence

The [source-video/GIS/SUMO overlay](../artifacts/reality/v8/geometry-video-overlay.png) uses an actual FHWA camera-4 frame, surveyed reference body centers, official GIS linework and marker, and native SUMO lane centerlines. The [geometry audit](../artifacts/reality/v8/geometry-development-audit.json) locates the modeled junction **5.65 m** from the official signal-89 GIS marker. That marker is not a surveyed stop line, so the offset is a warning rather than a calibrated positioning error. Mainline lane-center proximity on the development observations is often within about 1 m; it does **not** verify lane identities, turn bays, route permissions or stop lines. The current network has one intersection and lacks turn bays.

An initial route experiment forced all **63** completed observed turns through the one modeled Main Street junction. It was **rejected** after [GIS turn-location checking](../artifacts/reality/v8/turn-location-development-audit.json): the first observed turns were nearest official signal **88 for 48 vehicles**, **89 for 11**, and **90 for four**. Only **10** were within 50 m of the modeled signal-89 marker; 53 routes did not belong to the single-junction route correction. FHWA movement labels confirm turn class, not the intersection where it occurs. The rejected [63-route trial](../artifacts/reality/v8/reference-route-ablation-development.json) remains visible for audit and must not be cited as a valid route correction.

The [corrected Main Street oracle trial](../artifacts/reality/v8/main-turn-route-ablation-development.json) changes only those 10 source-located routes. On the same 1,441 development states, count MAE changes **1.333 to 1.319 vehicles**; native presence stays **93.41%**; within-4-m coverage changes **19.64% to 19.99%**; position MAE **worsens from 16.14 to 16.32 m**. Future completed destinations make this an oracle ablation, not a causal routing model or accepted physical improvement. A multi-junction corridor would be required to model turns at 88 and 90, but the present Main Street ROI must not reroute those vehicles prematurely.

## Controller records are not observed lamp states

The FHWA real-time split monitor (RSM) and archived timing sheet are authentic source material. The [RSM audit](../artifacts/reality/v8/signal-rsm89-audit.json) finds that the gap between adjacent report timestamps equals the **current row's cycle length for 875/875 pairs**. Thus each row timestamps a completed cycle; ATLAS 7 instead looks up the latest completed row as though it begins the next cycle. Report-row selection differs at all 1,122 video seconds. This **does not mean every displayed lamp was wrong**: the RSM contains green split totals, not exact phase-transition times, pedestrian calls or independently observed lamp colors. The available timing sheet is dated 2002, while the video is from 2005.

The [controlled end-of-cycle lookup ablation](../artifacts/reality/v8/signal-cycle-ablation-development.json) changes only that row assignment while keeping the old estimated two-stage phase onset, order and clearance. It **regresses** the 30–300 s CV run: presence **69.47% to 65.72%**, within-4-m coverage **18.74% to 18.11%**, position MAE **11.75 to 12.38 m**, and count MAE **1.478 to 1.630 vehicles**. The reference-initialized run also regresses. A correct report-row interpretation alone cannot fix an unverified phase model; it is not evidence that the old timing represented actual lamp states. The public reconstruction remains labeled an approximation.

## Cross-camera identity remains unresolved

The [CityFlow annotation audit](../artifacts/reality/v8/cityflow-annotation-audit.json) keeps the original S03 strict identity denominator and links intact. After the already frozen annotation convention, 9,420/9,948 annotated S03 boxes have a one-to-one predicted box at IoU ≥ 0.5, yet only **four of 18** annotated multi-camera vehicles have a verified accepted cross-camera link. The accepted S03 links include six checkable same-label cross-camera links, two unverifiable ones, and no checkable different-label cross-camera link. Many predicted boxes are in unannotated frames or belong to visible but unlabeled vehicles; the 16.7% prediction-to-annotation overlap is **not detector precision**. Weak cross-camera identity generalization remains a measured failure, not something solved by narrowing the denominator.

## Acceptance and next engineering gate

No source here establishes exact 2005 lamp transitions, a surveyed stop-line geometry, causal turn prediction, accurate future vehicle states, or a clean new holdout. The ATLAS 7 preregistered physical gate therefore remains failed. The Cologne RESCO MPC reduction remains a **separate simulated controller study**, not an observed Lankershim field improvement; ATLAS 8 controller promotion is blocked on physical validity.

The next defensible intervention is to recover independently checkable signal transitions (if the additional camera actually shows them), locate Main Street stop lines and legal lane-to-turn connections from the FHWA CAD/GIS/video, then run one-factor native SUMO ablations on development data. Freeze the candidate before selecting a genuinely new footage/reference cohort for acceptance. Do not tune against the already opened late tail or S03 identities.

## Reproduction and provenance

The raw FHWA video, NGSIM trajectory pages, RSM, survey files, full CV output and native FCD files are intentionally Git-ignored. `scripts/acquire_video_v6.py` verifies the complete official ZIP member with CRC and SHA-256. Source hashes and evaluated windows are recorded in each linked artifact; see the unchanged [ATLAS 7 reproduction instructions](reality-v7-results.md). With those local sources present, run the `scripts/*_v8.py` audits/ablations in their dependency order and execute `pytest backend/tests/test_*_v8.py`. The [FHWA NGSIM data dictionary](https://highways.dot.gov/media/87341) defines direction/movement codes; [FHWA Lankershim documentation](https://www.fhwa.dot.gov/publications/research/operations/07029/index.cfm) describes the corridor and camera study. Derived trajectory data follows the source CC BY-SA 3.0 terms; source video follows CC BY-SA 4.0. The overlay retains real source pixels and numerical observations, not synthetic benchmark imagery.
