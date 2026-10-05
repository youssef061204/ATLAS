# ATLAS technical report

## 1. Problem and product

ATLAS turns footage of one intersection into anonymous object trajectories, a synchronized digital twin, observation-derived analytics, and reproducible signal-control experiments. Its target user is an engineer inspecting an intersection or evaluating a control hypothesis. It is a local research platform; it does not operate roadside signals or certify near misses.

The interface separates measured video observations, synthetic learning experiments, and simulated interventions. Every benchmark comes from a generated JSON artifact. Empty states explain missing calibration, history, or ground truth instead of filling gaps with invented values.

## 2. Architecture and implementation choices

Next.js, React, TypeScript, Three.js, and Recharts render the product. FastAPI provides upload validation, camera configuration, result queries, run execution, OpenAPI, progress SSE, and Prometheus metrics. A bounded process pool executes CPU inference. SQLite WAL stores multi-intersection entities and indexed analytical records; local files hold footage and complete replay results.

Python keeps CV and numerical analysis together. A separate Go gateway would add a deployment boundary without improving this workload. Kafka, an external database, and Kubernetes are omitted because this implementation does not demonstrate a city-scale distributed workload. See [architecture](architecture.md) for data flow, migrations, concurrency, and schema details.

## 3. Source data, licensing, and provenance

The included demo downloads Mixkit #1755, an overhead time-lapse of Guadalajara. The source is 1,280 × 720, 480 frames, approximately 20 seconds, and 7.9 MB. Its SHA-256 and attribution are recorded. The repository contains a compressed, checksum-verified cache of an actual inference run; it contains neither the original footage nor model weights.

The aerial detector is a pinned upstream YOLOv8n VisDrone checkpoint with a verified checksum. The general camera profile uses YOLO11n COCO weights. Risk and forecasting experiments generate independent seeded data. COCO8 supplies a small integration evaluation. No matched tracking ground truth was obtained for the demo. Full sources, model revisions, license distinctions, and split rules are in [datasets](datasets.md).

## 4. Computer vision pipeline

OpenCV decodes the source. The detector interface wraps Ultralytics YOLO and persistent ByteTrack or BoT-SORT. It keeps cars, trucks, buses, motorcycles, bicycles, and people, with an explicit mapping for aerial model classes. Each detection carries a box, confidence, anonymous track ID, and source timestamp.

The generic COCO checkpoint performed poorly on the small overhead sample during qualitative inspection. The default demo therefore uses the aerial checkpoint at 960 pixels and processes every frame. This is a domain choice, not a quantified accuracy improvement: there is no matching annotated test set.

Trajectory points retain image and projected coordinates. Least-squares regression over recent timestamped observations estimates velocity; acceleration, heading, direction, stopped state, region membership, and entry/exit events follow from those tracks. Sampling preserves source timestamps. Track fragmentation and occlusion can inflate first-appearance counts and distort velocities.

## 5. Calibration and traffic analytics

Four or more non-collinear image/world control-point pairs fit a road-plane homography. Validation rejects non-finite or unstable inputs. Regions describe inbound/outbound approaches, crosswalks, waiting areas, stop lines, and intersection occupancy.

Verified calibration enables meter-based speed, density, and geometric safety screens. Without verification, motion remains in pixels per playback second, including when unverified control points are present. Verification is an operator assertion, not automated calibration certification. Image-ground contact points and a planar road are approximations.

Analytics expose class counts, current objects, first-appearance rates, speed statistics, stopped vehicles, queue estimates, stopped duration, dwell time, occupancy, road-user exits, direction counts, and entry-to-exit direction transitions. Queue estimates use inbound regions when configured. Unique IDs are not ground-truth unique road users. The time-lapse cannot supply physical speed or field arrival rates without a known recording time scale.

## 6. Digital twin and interaction

The observation twin uses actual projected or image-plane positions at the video clock. Selecting a detection or twin object opens its track details. Flow mode draws trajectories; heatmap mode accumulates recorded locations; safety mode highlights participating tracks. Regions share the same projection. Playback, seeking, speed controls, orbit/pan/zoom, and expansion operate on the replay.

The signal laboratory renders the portable simulation independently from footage. It shows protected signals, queues, and actual simulated vehicle positions on a shared comparison clock. It is a conceptual road network, not a reconstruction of surveyed lane geometry or a collision physics engine.

## 7. Safety screens and risk learning

Verified metric calibration gates safety processing. Constant-velocity closest approach supplies TTC and minimum separation. Recent path-segment intersections supply an interpolated center-point PET proxy. Acceleration supplies a hard-braking screen. Alerts have participants, time, severity, confidence, an explanation, and source replay. Cooldowns suppress repeated pairs. PET excludes body extents; all screens require human review and can produce false positives under tracking noise.

The learning experiment compares standardized logistic regression with histogram gradient boosting. Noisy observed features include TTC, separation, relative speed, angle, vulnerable-road-user presence, acceleration, and nearby count. Labels come from hidden accelerated future motion, not a threshold applied directly to the input feature vector. Train/validation/test seeds are 1001/2002/3003 with 6,000/2,000/3,000 cases. Validation selects the threshold and winning model; test data does not select either.

The selected synthetic model scored AUROC 0.974, AUPRC 0.824, F1 0.764, Brier 0.041, and ECE 0.010. At its validation-selected threshold, test precision was 0.731 and recall 0.800. The confusion matrix was TN 2,534, FP 106, FN 72, TP 288. False alerts per hour remain null because generated pairs have no measured exposure time. These numbers describe the generator, not road-safety accuracy. Serialized models are reproducible local outputs excluded from source control; runtime uses geometric screening when a trained model is absent.

## 8. Forecasting and leakage controls

Source forecasting bins observed active vehicles by minute. It requires at least 15 minutes of source history and uses a causal moving-average baseline at 5/10/15 minutes. Its spread is exploratory, not a calibrated prediction interval. The short demo correctly returns insufficient history.

A separate ML experiment generates a 2,880-minute diurnal series with seed 4444. Thirty-minute causal history features feed histogram gradient boosting. Historical mean, persistence, and moving average are explicit baselines. Training targets end before minute 1728; test origins begin at 2304. Boundary-crossing targets are purged. The intervening validation period is reserved but unused because hyperparameters are fixed; it is not reported as a tuned model.

At five minutes, held-out gradient-boosting MAE was 2.466 and RMSE 3.086, versus persistence MAE 2.706 and moving-average MAE 2.565. JSON contains all three horizons, MAPE with low-volume exclusions, and actual-versus-predicted previews. Synthetic models are not silently substituted for forecasts on uploaded footage.

## 9. Portable traffic simulation

The default engine is a deterministic, single-lane, four-approach simulator with half-second steps. Seeded Poisson arrivals are shared across all policies. Vehicles accelerate toward 12 m/s, brake for the stop line, and maintain a leader gap. A two-phase controller protects opposite straight-through movements with yellow and all-red clearance. Pedestrian arrivals wait for a compatible phase start and reserve the configured service interval.

Delay includes completed and unfinished vehicles and off-network insertion waiting. Insertion waiting remains attached to a vehicle after it enters the network. Per-approach delay includes remaining insertion queues, so fairness penalties cannot hide excluded demand. Pedestrian wait includes unserved pedestrians at the horizon. Conservation, minimum gap, signal clearance, empty demand, and seed reproducibility have automated checks.

The portable engine does not model turning traffic, heterogeneous vehicle dimensions, lane changing, moving pedestrian bodies, full junction collision geometry, or network spillback. The optional SUMO comparison introduces a vehicle-class mix independently; it does not remove these default-engine limitations.

## 10. Signal optimization and equivalent-demand comparisons

Baselines are fixed 30/30-second timing and queue-responsive adaptive control bounded by minimum/maximum green and clearance constraints. ATLAS evaluates a constrained grid of green splits. Candidate selection uses two distinct tuning arrival seeds; the selected timing is replayed against the baselines on the same held-out test arrivals.

The objective combines mean vehicle delay, pedestrian waiting, maximum queue, and worst-approach delay. The UI exposes final and replay-time metrics for all three policies. The experiment repeats on seeds 42, 43, and 44, with a measured mean delay reduction of 37.5% and standard deviation 5.4 percentage points against fixed timing. Selected candidates, objective values, timings, environment, and per-policy metrics are in [simulation.json](../artifacts/simulation.json). Rerunning after a model change replaces the measured result.

An independent SUMO 1.27.1 cross-check uses the same seeded arrivals, four straight-through routes, one lane per approach, explicit clearance phases, and cars/trucks/buses/motorcycles. It compares fixed timing to the split selected by the portable simulator, without optimizing directly in SUMO. The comparison is one seed and excludes pedestrians and turns. Mean reported delay includes SUMO-reported unfinished trips and departure delay, but excludes demand not yet inserted. Throughput and remaining demand are reported beside it to expose this denominator limitation. See [sumo.json](../artifacts/sumo.json).

## 11. Performance and scaling measurements

The standalone CPU aerial run processed 480 frames in 24.632 seconds: 19.487 sampled FPS, 40.773 ms median and 55.411 ms p95 detector/tracker latency, 585 MB worker RSS, and 2.794 seconds to first measured result. This is offline pipeline throughput on the recorded Windows machine, not a GPU claim or guaranteed live frame rate. Cache restoration does not generate a new inference benchmark.

Actual concurrent inference achieved 19.07 aggregate sampled FPS for one process and 23.05 for two, showing CPU contention rather than linear scaling. The mixed health/database/metric-query load experiment made 2,650 requests with zero errors. At 1/4/16/32 clients, p95 latency was approximately 29.5/97.8/838.4/2,013.1 ms. High concurrency saturates this local implementation. Other development work could affect these measurements; they are not isolated infrastructure capacity tests.

Prometheus reads persisted worker measurements, avoiding misleading process-local counters. Progress SSE contains stage, progress, current observations, and timestamps. Full result JSON duplicates trajectory and frame data and is held in memory; a long-recording implementation should partition replay files and use paginated analytical reads. Multi-intersection IDs exist, but city-scale capacity is unmeasured.

## 12. Evaluation infrastructure and reproducibility

`atlas evaluate` generates risk, forecast, and simulation artifacts. Optional detection evaluation runs YOLO11n on COCO8's four validation images: precision 0.570, recall 0.850, mAP50 0.846, and mAP50:95 0.630. This verifies integration; it is not a traffic accuracy benchmark. Official TrackEval accepts matching MOT-format annotations for HOTA, IDF1, MOTA, ID switches, and fragmentation. Its analytic self-test is stored separately and never presented as field tracking quality.

Generated artifacts carry scope, seed/splits, environment, and timestamps. The CSV exporter flattens numeric results with their scope. Model weights and datasets are separately downloaded; Python direct dependencies and frontend lockfile are pinned. `requirements.lock` records the Windows environment snapshot; Linux uses explicit CPU PyTorch wheels. The clean Docker build provides a tested second environment.

## 13. Reliability, security, and privacy

Upload validation bounds size and duration, sanitizes storage names, and probes decodability. Processing errors become failed jobs with a recovery action. API restart marks interrupted jobs failed instead of leaving indefinite progress; CLI initialization does not interfere with active jobs. The process queue is bounded. Models download lazily; an unavailable model host causes an explicit failure. Health checks exercise database access. Bootstrap validates checksums for both source and cached results and reuses matching completed cache records.

Docker binds loopback. This is a trusted local API without public user authentication. Stream capture is disabled by default and requires a hostname allowlist; live network capture remains an optional path. Data persists locally until removed by the operator. No identity matching, facial recognition, cross-camera person association, external LLM requests, or hosted footage upload occurs. Public deployment needs authentication, quotas, network controls, and a retention policy. See [API/security](api.md).

## 14. Findings and remaining work

The application demonstrates actual detector/tracker output, synchronized replay, analytical persistence, constrained control search, synthetic model comparison, official metric integration, and measured CPU/API performance. It also exposes the difference between running a model and proving field accuracy.

The real-data upgrade below measures vehicle detection, identity continuity, annotation-derived counts, chronological highway-speed forecasting, and multi-seed SUMO control with turns. Surveyed speed, queue error, calibrated conflict precision/recall, exposure-based false alert rates, pedestrian control, and field interventions remain outstanding. GPU, RTSP/webcam transport, public authentication, and city-scale load remain unverified extensions.


## 15. Real-world evaluation upgrade

The complete, reproducible methodology, acquisition instructions, dataset licenses/references, class mapping, preprocessing, split integrity, metrics, and threats to validity are in [Real-world evaluation protocol](real-world-evaluation.md). This extends the original controlled suite described above; it does not replace or relabel it.

**detection** ? real, UA-DETRAC. Real annotated traffic, predeclared UA-DETRAC subset. Not a full UA-DETRAC challenge score or its PR-MOTA protocol. [Measured JSON](../artifacts/benchmarks/real_detection.json).

**tracking** ? real, UA-DETRAC. Real annotated traffic, predeclared UA-DETRAC subset. Not a full UA-DETRAC challenge score or its PR-MOTA protocol. [Measured JSON](../artifacts/benchmarks/real_tracking.json).

**traffic_analytics** ? real, UA-DETRAC. Real annotated traffic, predeclared UA-DETRAC subset. Not a full UA-DETRAC challenge score or its PR-MOTA protocol. [Measured JSON](../artifacts/benchmarks/real_analytics.json).

**forecasting** ? real, METR-LA. Real highway speed observations in mph; all 207 sensors. Temporal univariate models, not a graph-network benchmark or intersection-count forecasting validation. [Measured JSON](../artifacts/benchmarks/real_forecasting.json).

**systems** ? real, UA-DETRAC. Actual annotated traffic frames encoded losslessly at the published 25 FPS. Fresh complete production pipeline runs; includes initialization, analytics, SQLite and JSON persistence. CPU only. [Measured JSON](../artifacts/benchmarks/real_video_pipeline.json).

**signal_control** ? real-world-derived, RESCO Cologne1. Published Cologne SUMO network and modeled demand derived from real-world data; simulated interventions, not measured field delay improvements. Held-out demand period and seeds. [Measured JSON](../artifacts/benchmarks/realistic_signal_control.json).

**safety_qualitative** ? real, UA-DETRAC. Real-world qualitative / trajectory-based validation is limited to verifying the calibration gate on real footage. No real conflict accuracy or physical trajectory validation is claimed. [Measured JSON](../artifacts/benchmarks/real_safety_qualitative.json).

The pretrained baseline achieved vehicle mAP@50 0.898 and mAP@50:95 0.626; IDF1 0.793, HOTA 0.640, MOTA 0.683, matched IoU MOTP 0.834, 151 identity switches, and 445 fragments. Counts achieved 1.302 MAE and 2.016 RMSE; fragmentation still substantially inflates unique-track counts. These selected 4,260 frames are three complete official test sequences, not full challenge scores. No vision tuning or fine-tuning was performed.

METR-LA ML MAE was 2.490/2.895/3.214 mph at 5/10/15 minutes, versus persistence 2.813/3.207/3.498. This evaluates temporal highway-speed models on all 207 sensors; the current runtime five-bin smoother is also reported and is weaker than the ML model. Chronological 70/10/20 splits, training-only fitting, target masking, and timestamp-gap exclusion protect evaluation. It does not prove intersection-count forecasting accuracy.

The complete CPU pipeline achieved 29.419 FPS, p50/p95/p99 inference latency 28.777/35.694/40.850 ms, peak sampled RSS 634.8 MiB, 50.99 processing seconds per minute of source footage, and 29.4% logical CPU capacity. Original aerial throughput remains separate because model, footage, resolution, and sampling differ.

RESCO held-out mean delay ? sample SD was fixed 57.45?0.53 s, adaptive 84.01?1.72 s, max-pressure 37.99?1.75 s, and ATLAS 66.45?0.66 s, three paired seeds each. Search selected only on the preceding period increased held-out delay by 15.7%; max-pressure reduced it. This negative result exposes limited controller transfer under demand shift and is retained. Delay includes all 889 scheduled vehicles per run, including unfinished/not-inserted demand. Per-seed time series, queues, stops, travel, completion, and fairness estimates remain in JSON.

Safety-engine invocation on all real frames verified that absent metric calibration suppresses physical conflict screens; zero generated events is not a safety score. No TTC/PET distributions or supervised real conflict accuracy can be validly supplied from these uncalibrated annotations. Calibrated labeled conflict evaluation remains explicitly incomplete.

## Signal-controller engineering iteration

The original failed timing search remains published (66.45 s versus fixed 57.45 s and max-pressure 37.99 s on three historical seeds). It used a demand-independent cycle and excluded the fixed schedule from its six-candidate search. The replacement uses source legal phase masks, causal lane-arrival prediction and a 30-second, six-beam receding-horizon queue model selected on separate validation demand.

Ten new paired Cologne1 seeds measured **20.53 +/- 0.85 s** mean delay: **65.7%** paired reduction versus fixed and **45.3%** versus unchanged max-pressure. The mean 95% interval is 19.92-21.13 s; both paired bootstrap improvement intervals exclude zero. All original/fixed/max-pressure/new per-seed results, losing candidates, diagnostic plots, ablations and transfer results are preserved.

Untuned Ingolstadt1 transfer failed: new ATLAS 40.08 s, fixed 37.95 s, max-pressure 28.16 s across five seeds. Forecasting adds only a small, uncertain ablation benefit. The shared final evaluator uses Linux SUMO 1.27.1 after detecting native Windows same-seed drift; CV and highway forecasting measurements are unchanged. See the [complete audit](signal-control-audit.md) and [final results/reproduction](signal-control-results.md) for constraints, split design, confidence intervals and limitations. The public optimization page plays genuine sampled final-test SUMO output; it does not run SUMO on Vercel.
