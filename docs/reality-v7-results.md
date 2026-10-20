# ATLAS 7: real video, measured reconstruction

ATLAS processes actual consecutive traffic video, reconstructs observed tracks,
runs native free-running SUMO, and presents both on one playback clock. The
public application serves historical video and precomputed real processing.
Python/OpenVINO live workers run natively; Vercel does not host those workers.
No paid model service or additional infrastructure was used.

[Video and 3D replay](https://atlas-mu-murex.vercel.app/reality) ·
[Interactive experiments](https://atlas-mu-murex.vercel.app/benchmarks) ·
[Exact artifacts](../artifacts/reality/v7) ·
[Preserved ATLAS 6](reality-v6-results.md)

## What actually ran

**49,979 newly processed consecutive frames across 13 complete videos:**

| Source | Full CV runs | Frames | Scope |
|---|---:|---:|---|
| NGSIM Lankershim camera 4 | 1 | 11,220 | Complete 18:42 raw recording; every frame |
| NGSIM Peachtree camera 1 | 1 | 14,961 | Complete 24:56 raw recording; independent-city perception test |
| CityFlowV2 S01 | 5 | 10,281 | Development camera group |
| CityFlowV2 S03 | 6 | 13,517 | Frozen held-out camera/intersection group; c015 is 8 FPS |

The separate Peachtree camera 5 acquisition was fully decoded for integrity,
not passed off as completed CV inference. The four retained CityFlow S02 runs
and their 8,109 frames remain an earlier experiment. Raw datasets, crops,
embeddings, model caches and full result caches stay outside Git.

FHWA video/support acquisition verifies archive ranges, CRC, source SHA-256 and
actual decoding. ZIP integrity alone does not establish internal AVI integrity:
all five second-recording Lankershim files have truncated internal headers. The
qualified ATLAS 6 prefix experiment remains explicitly incomplete.

## Perception: comparable improvement, separate failures

These Lankershim scores use the **same known 600–1,000 s validation interval,
fixed region, independent reference observations, 1 Hz points and 4 m gate**.
They are not bounding-box IDF1 or mAP. Geometry is fitted only on 0–300 s.

| Metric | Retained ATLAS 6 raw | ATLAS 7 raw | Offline continuity/gaps, separate |
|---|---:|---:|---:|
| Point IDF1 | 0.68523 | **0.72589** | 0.74065 |
| Matched reference coverage | 60.674% | **65.843%** | 68.390% |
| CV visible-count MAE, vehicles | 2.2125 | **1.8775** | 1.7050 |
| Conditional matched position MAE, m | 1.2128 | 1.2359 | 1.2404 |
| Conditional matched speed MAE, m/s | 0.7808 | 0.8049 | 0.8125 |

Reference denominator: 2,670 observations. Raw ATLAS 7 has 1,758 spatial matches.
The secondary result includes **89 inferred observations at scoring cadence**;
interpolated boxes are hidden by default and explicitly marked when enabled.
They use a future endpoint and cannot be called live detections. The full
recording contains 11,663 such box estimates; track IDs are not unique vehicles.

Development compared full-frame, higher-resolution, tiled and larger aerial
models, trackers, gap thresholds and an FP32 runtime transfer. Full 960 px plus
two overlapping 640 px crops won the declared development selection. A larger
YOLO11s aerial model did not win; COCO YOLO11n had no usable aerial detections
in that development clip. Longer interpolation regressed identity/speed and
was rejected. Exact settings and sources were frozen before test scoring.

The reserved same-camera 1,020–1,120 s tail remains weak: raw point IDF1
**0.12559 → 0.15686**, count MAE **4.53 → 4.55**. No new reference identity
starts after 1,019.9 s, so the strict fresh-track test has **zero eligible
reference states** and is unestimable. An archived scorer correction handles
that empty denominator without changing matching or cohorts. Post-outcome
annotation-coverage and image-registration diagnostics do not replace scores.

## Peachtree: independent city and camera

The Lankershim-selected model is unchanged. Peachtree image/world/time
registration uses only the first 300 s; a four-frame raw-video offset is frozen
from three image checks. Two spatial checks give 0.7004 m RMSE. A pre-test
east/west heading-fallback correction leaves all eight calibration controls
unchanged but worsens the 12-point temporal check from 1.5364 to **2.1857 m**.
Original and corrected evaluator sources are archived. These diagnostics are
not global calibration confidence bounds.

| Frozen 600–900 s cohort | Reference states | Point IDF1 | Coverage | Count MAE |
|---|---:|---:|---:|---:|
| Full window | 3,543 | 0.49014 | 61.248% | 4.440 |
| Calibration-disjoint identities | 3,543 | 0.49014 | 61.248% | 4.440 |
| Fresh identities after 600 s | 2,924 | 0.45863 | 60.876% | 4.803 |

Full-window conditional matched position MAE is 1.9139 m and speed MAE is
0.5233 m/s. These errors depend on matching and must be read beside coverage.
All predeclared cohorts are reported; none is substituted for another.
Annotations end before the full video does. No accuracy claim covers the
unannotated tail, and no Peachtree physical SUMO acceptance is claimed.

## Physical reconstruction: improvement with an explicit failed gate

The native Lankershim run covers all 1,122 s. Each requested CV birth supplies
one observed interior pose and past-only speed, followed by free-running SUMO.
This changes conditioning from ATLAS 6's outer-boundary-only experiment; its
count change cannot be attributed solely to better physics.

Nine development-only desired-speed/following-time candidates selected
15.65 m/s and tau 0.7 s. Lower uniform speeds failed. A diagnostic exposed
edge-level insertion blocking: one failed interior insertion could delay
other births at different positions on that edge. Native `--eager-insert`
checks each pending birth separately while retaining every safety check.
Its selection uses only 0–300 s and a missing-prediction-penalized objective.
No reference state forces simulation after admission. No collision, signal,
insertion or braking check is disabled.

| Known 600–1,000 s regression | Original birth model | Tau selected on development | Development-selected eager insertion |
|---|---:|---:|---:|
| Uncapped native position MAE, m | 16.712 | 15.837 | **13.644** |
| Reference states within 4 m | 9.064% | 10.075% | **12.659%** |
| Native visible-count MAE, vehicles | 2.790 | **2.715** | 2.860 |

The public replay uses the final column, including its count regression.
Missing predictions stay in the coverage denominator; large physical errors
are not removed by the 4 m birth-association gate. Final native presence covers
54.569% of reference states. Queue MAE is 0.8325 vehicles, matched native speed
MAE 2.9754 m/s, directional flow normalized absolute error 0.4167, and worst
unpaired traversal-distribution Wasserstein distance 2.1836 s. Requested start
times and first actual 1 Hz native samples are distinguished in the inspector.

**No intersection passes the preregistered physical acceptance criteria.**
Position, coverage, counts, flow, speed, traversal distribution and independent
signal confirmation fail applicable gates. Queue error alone is insufficient.
Missing turn bays, uncertain lane geometry, occlusion, duplicate/missed CV
births and simplified RSM stages remain material. Independent lamp-state
observations are unavailable for this reconstruction. All acceptance criteria
remain unchanged in [the protocol](reality-v7-protocol.json).

New controller promotion is therefore deferred. Retained Cologne MPC results
(65.7% versus fixed, 45.3% versus max-pressure over ten seeds) are a **separate
RESCO simulation study**, not intervention results for this observed video.
The ATLAS 5 selector's failed worst-case promotion remains preserved.

## Multi-camera research

S01 development selected pretrained vehicle-specific OSNet-AIN descriptors,
geometry/time gates and a 0.55 cosine handoff threshold. Same-observation
annotation-aligned IDF1 was 0.34428 for independent camera IDs and **0.51621**
after association; the weaker color-descriptor candidate was 0.51521.

S03 was frozen before label scoring. Across all six complete videos:

| Identical 56,337 predicted boxes | Independent IDs | Geometry only | Geometry/time/vehicle ReID |
|---|---:|---:|---:|
| Raw-box IDF1 | 0.16354 | 0.16354 | **0.16491** |
| Annotation-aligned, +10 px per edge | 0.16474 | 0.16474 | **0.16635** |

The gain is small. Filtering to cross-camera-linked identities changes the
prediction cohort and regresses to **0.08541**; it is not a headline result.
S01/S03 are different Dubuque intersections, not different cities. Annotation
padding follows the official box convention, not better physical localization.
Only multi-camera vehicles are annotated, so the primary false-positive
denominator includes visible single-camera predictions.

The older S02 baseline 0.26012, failed appearance result 0.22027 and initial
geometric ablation 0.26314 remain published. No official challenge or universal
generalization claim is made. CityFlow raw media, GT, crops, descriptors and
GPS trajectories are not redistributed under its noncommercial research terms.

## Genuine live video

- **Caltrans I-5 / Disneyland Drive HLS, nighttime:** six consecutive segments,
  60 source seconds, 1,500 decoded frames, 500 inference frames, 499 frames
  with predicted tracks, no stream-gap identity reset. FP32 Intel integrated
  GPU inference p95 78 ms; RSS 509 MB. Actual car ID continuity was visually
  checked two seconds apart. Segment-receipt-to-result p95 is 9.984 s, not
  camera-to-display latency. Earlier zero-track and slow/dropped-segment trials
  remain archived.
- **Taiwan Freeway Bureau camera 21840, daytime MJPEG:** 60.016 s, 258/258
  MJPEG frames decoded/inferred (258 distinct compressed-JPEG hashes), 142 frames with predicted tracks,
  4.299 effective decoded FPS, p95 inference 63 ms. Five provider disconnects
  cause explicit identity resets; maximum receipt gap is 2.468 s. Actual
  daytime pixels and car boxes from this same camera were inspected in the
  preceding trial. Later follow-up images expired without inspection and
  support no extra visual-continuity claim.

Both are continuous video transport, not still-image polling. TLS verification
stays enabled. The Taiwan source required the HTTPX CA bundle; an initial
urllib trust failure and metadata timeout remain recorded. Provider and
licensing provenance are linked in artifacts. Attribution: **Taiwan Freeway
Bureau, 2026, CCTV static information v2.0 and linked public road camera video,
Open Government Data License v1.0**. Caltrans provides free integration and
public-domain agency material. These are scoped interpretations of published
agency notices, not bespoke permission or provider endorsement.

Only bounded transient buffers are used. Temporary source media/audit images
are deleted; no raw live video is committed or publicly redistributed. Neither
trial has independent tracking/count/speed ground truth. Track diagnostics are
not unique-vehicle counts. Archived telemetry is never current public traffic.

## Video forecasting and preserved highway results

A fixed chronological pilot predicts the independent **mean visible-vehicle
count in a future 30 s window** from trailing actual raw-CV counts. All training
targets end before 600 s; all test forecast origins start at/after 600 s.

| Horizon | Test origins | Raw CV persistence MAE | Training-mean MAE | Fixed ridge MAE |
|---|---:|---:|---:|---:|
| 1 min | 32 | 3.974 | 2.198 | **1.839** |
| 3 min | 20 | 3.272 | **2.723** | 2.798 |
| 5 min | 8 | 3.033 | 1.967 | **1.545** |

Units: vehicles, not mph or flow. Overlapping targets are not independent
samples. The five-minute origins cover only 70 s; no robust long-horizon,
cross-city or calibrated-uncertainty claim follows. The source does not support
honest chronological 15/30 minute evaluation. These are a pilot, not controller
promotion evidence. The earlier METR-LA results remain separate: classical
2.490 versus persistence 2.813 mph, and directional GNN 2.344 mph at five minutes
across 207 highway sensors, one seed and the shared historical test period.

## Interface, runtime and reproduction

Real HTML video controls drive actual detector boxes and native 1 Hz SUMO
states. Play, pause, frame step, scrubbing and speed share one clock. Display
interpolation is not a new physical observation. Selecting a vehicle links its
video box, 3D representation, actual/inferred observations, source tracker IDs,
gaps and requested/observed native starts. Follow, angled, street and top-down
cameras, orbit/pan/touch, a 2D fallback and layer controls remain available.

The 3D scene uses FHWA road survey linework, a georeferenced historical
orthophoto, native curved lanes and modeled signal states. Instanced original
vehicle geometry includes bodies, cabins, wheels and lights. Buildings/tree
context and heights are illustrative. Static cars in the orthophoto are
background imagery, not current observations. Projections outside the spatial
calibration hull are grey with physical speeds withheld. Offline estimates are
amber and hidden by default. Native/CV layers stay distinguishable.

Complete Lankershim multiscale **CPU throughput is 4.803 FPS**, including
processing/persistence under shared-host load; no real-time claim. Complete
Peachtree **OpenVINO FP32 integrated-GPU throughput is 5.212 FPS**. A 1,200-frame
development runtime equivalence check reproduces raw point IDF1 and coverage
exactly before GPU transfer. These workloads do not replace the historical
UA-DETRAC **29.4 FPS CPU**, 0.898 mAP@50 and 0.793 IDF1 benchmark.

Paused rendering uses demand mode and software renderers select reduced
graphics cost. Rendering and page performance must be measured separately
from inference FPS; see release verification/media records for actual checks.

The production-browser rendering comparison uses the same 1,440 x 1,000 viewport,
600 s replay position, angle, video playback and CV/SUMO layers. All browsers
actually reported SwiftShader, so this is software rendering, not a physical-GPU
benchmark. The default-browser full-cost pass improves **9.32 to 14.65 FPS**;
reduced cost improves **12.46 to 19.24 FPS**. Historical-photo material changes
and instanced modeled signal heads reduce work without changing the observations.
The explicit software-control passes measure **9.43 to 12.00 FPS**, and
**12.30 to 60.00 FPS** reduced cost. That last pass is unusually fast relative
to the other profile with the same reported renderer. These are single passes
on a shared host, without confidence intervals; the 60 FPS outcome is not a
general performance promise. Video progressed over ten seconds in every window.
Initial readiness including the deliberate 2.5 s settle is 12.94/3.28 s for the
two final browser profiles. All passes and exact before/intermediate/final scene
sources are retained in `artifacts/reality/v7/render-*`.

Five actual application screenshots and a **48.4 s / 1,210 decoded-frame**
walkthrough are published in `artifacts/portfolio/v7`. The movie removes initial
loading and changes web compression only. It shows real video/3D correspondence,
physical failures, independent experiments and the separately scoped retained
RESCO controller comparison. The media manifest binds exact presentation source
and underlying evidence hashes; attribution/share-alike notices accompany it.

Run `python scripts/verify_v7_evidence.py` to verify public source archives,
SHA-linked replay/native outputs, frozen scoring, denominator arithmetic,
empty-cohort handling, live continuity and forecast chronology. This portable
audit does not pretend to rerun inference or access private ground truth.
Source acquisition, complete processing, evaluation and publication scripts are
provided separately. Install `.[evaluation,geospatial,accelerated]` for the full
research workflow. `scripts/publish_replay_v7.py` and
`scripts/publish_research_v7.py` rebuild the authentic public assets; frontend
preparation verifies every asset against its manifest. Do not overwrite frozen
experiments or tune on held-out outcomes.


### Current live-runtime recheck

On the later release session, OpenVINO exposed CPU only. The optional GPU
worker correctly refused to claim execution; no driver changes were attempted.
An explicit CPU recheck then processed 95 actual MJPEG frames in a requested 30 s trial (33.422 s
measured wall time including connection cleanup), 68
with tracks. Two temporary source frames were actually viewed, with provider
clocks 08:33:31 and 08:33:32 Taiwan time on October 20: a yellow box truck
and orange flatbed visibly move along the road. IDs may fragment; no same-ID
accuracy is inferred. Images were deleted as required. This is separate from
the archived October 17 GPU timing result, not a same-workload speed comparison.
