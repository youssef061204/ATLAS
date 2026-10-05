# Real-world evaluation protocol

The production architecture is unchanged. Evaluation adapters call the existing detector, persistent tracker, trajectory analytics, and complete video processor. Real measurements and controlled experiments occupy separate dashboard sections. Committed JSON contains measured results; raw recordings, sensor data, model outputs, and SUMO logs stay in ignored `datasets/` and `artifacts/models/` directories.

## Reproduction

Use Python 3.11 and the project virtual environment. Install optional dependencies once:

```sh
pip install -e '.[dev,evaluation]'
python scripts/prepare_real_data.py
python scripts/evaluate_real.py
python scripts/standardize_benchmarks.py
python scripts/export_artifacts.py
```

On Windows substitute `.venv/Scripts/python` and `.venv/Scripts/python -m pip`. Dataset preparation uses pinned public mirrors and requires network access. It selects three complete UA-DETRAC test sequences and 150 frames from each of two training cameras; `--frames 300` instead creates an explicitly smaller prefix experiment. `--only detrac`, `--only metr`, or `--only resco` limits acquisition. All downloaded content is local and is never sent to an external service.

An official or approved copy of the mirror-format ZIPs can be used without range downloading:

```sh
python scripts/prepare_real_data.py --only detrac --local-archives /path/to/archives
```

Expected filenames are `ua_detrac_test_set.zip` and `ua_detrac_training_set.zip`. These are the pinned mirror's image-plus-CSV archives, not the original XML annotation archives. Download source/version/terms are listed below. The original author's image links currently require Google sign-in and the legacy annotation hostname redirects to a lab page; the mirror makes this run reproducible without an account. If that mirror becomes unavailable, obtain approved archives and use the local option. Local archives are recorded with per-member checksums and must retain the documented CSV contract; they are not silently assumed to be byte-identical full remote archives.

`make prepare-real-data`, `make evaluate-real-detection`, `make evaluate-real-tracking`, `make evaluate-real-forecasting`, `make evaluate-signal-control`, `make benchmark-real-video`, `make evaluate-real`, and `make evaluate-all` provide equivalent targets. Detection and tracking share a single evaluation pass. `--reuse` recalculates metrics from cached predictions only after verifying source images, original CSV, converted annotations, manifest, weights, and configuration. Omit it for fresh inference. `evaluate_real.py` runs every prepared dataset and clearly skips absent datasets; a specifically requested missing dataset fails. No evaluation command implicitly downloads a dataset. Errors in prepared data fail rather than becoming fabricated scores.

## Sources, versions, and rights

| Data | Primary reference | Pinned acquisition | Usage terms |
|---|---|---|---|
| UA-DETRAC | [Author's dataset page](https://sites.google.com/view/daweidu/projects/ua-detrac); Wen et al., *UA-DETRAC: A New Benchmark and Protocol for Multi-Object Detection and Tracking*, CVIU 2020 | [Research mirror](https://huggingface.co/datasets/abhineet123/ua_detrac), revision `72045f434a646e6dc9b04e251a4108705cdfa5bf` | Mirror declares CC-BY-4.0; original author's rights and research usage terms take precedence. The mirror declaration is not a new license granted by ATLAS. No raw redistribution or commercial rights assertion. |
| METR-LA | [Li et al., DCRNN data and repository](https://github.com/liyaguang/DCRNN), ICLR 2018 | [SkyTraffic mirror](https://huggingface.co/datasets/MintBruce/SkyTraffic), revision `800700306275910dcfbb0ac3977c12e72e81f24a` | Mirror declares `other`; the DCRNN code's MIT license does not establish the underlying sensor-data license. Research evaluation only; consult original terms before further use. |
| RESCO Cologne1 | [Ault and Sharon, RESCO repository](https://github.com/Pi-Star-Lab/RESCO), *Reinforcement Learning Benchmarks for Traffic Signal Control*, NeurIPS Datasets and Benchmarks 2021 | Commit `f1ed9a174f8de41fc9d8689373b836bc882570dc` | Downloaded Cologne1 scenario LICENSE is **CC BY-NC-SA 3.0**. RESCO code is separately GPL-3.0. Attribute the scenario; observe noncommercial and share-alike terms for redistributed adaptations. ATLAS does not redistribute raw scenario files. |

METR-LA HDF SHA-256 is `64784b76d6fb8ec9bff4b6decafb354da2bb37840468fdccee5044e511277c05`. Each RESCO network/demand/config/license file has a pinned SHA-256 in `backend/atlas/evaluation/data.py`. UA-DETRAC uses selective HTTP ranges rather than downloading both 4.25/5.63 GB archives; ZIP CRC verifies extracted members and the manifest records SHA-256 for every image and source CSV. A full-archive SHA-256 is **not** claimed for partial downloads. Range responses must be valid 206 responses with matching ranges and lengths. Mirrors can have undocumented transformations; that is a threat to equivalence with the original challenge release.

## Untouched vehicle baseline

The ATLAS general detector is pretrained COCO YOLO11n, Ultralytics 8.4.173, checkpoint SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`. The separate aerial demo profile is YOLOv8n-VisDrone and is not substituted into this road-camera evaluation. All 4,260 frames from predeclared official test cameras **MVI_39031 (1,470), MVI_39211 (1,660), MVI_40701 (1,130)** are evaluated at 25 FPS source cadence, 640-pixel inference, and `sample_every=1`.

Two different cameras, MVI_20011 and MVI_20012, belong to the official training partition and are reserved as a small validation resource. No detector fine-tuning, confidence selection, or tracker tuning was performed after observing test results. Baseline quality justified preserving this configuration; full training data was not acquired. The initial 900-frame pilot remains in `real_detection_pilot900.json` and companion artifacts rather than being hidden by the larger result. Three selected cameras are a limited subset of the official 40-sequence test partition: **these are not full challenge or PR-MOTA leaderboard scores**.

The mirror collapses original vehicle types into `vehicle`. Predictions for COCO car, motorcycle, bus, and truck map to that one compatible category; people and bicycles are excluded. Subclass AP is unavailable. `per_class_ap.vehicle` is the merged AP. Boxes use source pixel coordinates and identities are sequence-local.

Detection AP uses official pycocotools COCOeval, confidence floor 0.001, NMS IoU 0.7, maxDets 100, IoUs 0.50:0.05:0.95. Ignored regions become COCO crowd annotations. Precision/recall/F1 use confidence 0.25 and maximum-cardinality assignment at IoU 0.5. Crowd IoA exclusion is deliberately stated; it differs from an unspecified challenge protocol.

Tracking calls production `YOLOTracker.infer` with persistent ByteTrack, reset between cameras. Unmatched predictions inside an ignored region with prediction-area overlap >0.5 are removed, after valid annotation matching protects true positives. Official TrackEval HOTA, CLEAR, and Identity metrics use their standard `combine_sequences`, rather than averaging sequence scores. HOTA averages its official IoU grid; CLEAR/identity use 0.5. MOTP is matched-box IoU, larger is better. Artifacts include per-sequence metrics and global ID switches, FP, FN, and fragmentation.

## Annotation-derived analytics

Production `TrajectoryEngine` active vehicle counts are compared to valid per-frame annotation counts after the same ignored-region policy. Global MAE/RMSE weight every frame equally. Per-camera unique predicted tracks are compared to annotated identities, with relative error. Fragmentation causes substantial overcounting and is visible in the raw artifact; stable per-frame counts do not establish accurate unique road-user counts. Direction/crossing counts lack predeclared virtual gates. Physical speed, queue length, physical occupancy, and road-plane safety metrics lack surveyed calibration or matching labels and remain unvalidated.

## Real forecasting

METR-LA contains 34,272 native five-minute records from 207 highway sensors; the target is **speed in mph**, not intersection volume. Fixed-format HDF arrays are read directly with PyTables to avoid legacy pandas metadata incompatibilities. Sensor and timestamp alignment are checked.

Chronological split: train 2012-03-01 through 2012-05-23 07:05; validation 2012-05-23 07:10 through 2012-06-04 04:40; test 2012-06-04 04:45 through 2012-06-27 23:55. Original timestamps are preserved; horizons do not cross missing-date gaps. Training targets finish before the split boundary, while validation/test forecast origins begin within their respective partitions. Causal history from the preceding partition is valid information available at the prediction time.

Six native bins provide 30 minutes of causal history. Missing/nonpositive history is forward-filled; initialization uses training-only medians. Missing/nonpositive targets are excluded. MAE/RMSE include all valid targets; MAPE includes only targets >=5 mph, with both denominators recorded. SMAPE is also reported. No random time split, future interpolation, sensor adjacency, or test-based selection is used.

All horizons compare last-value persistence, training-only sensor historical mean, three-bin moving average, the current five-bin ATLAS runtime smoother, and the existing histogram-gradient-boosting model family retrained exclusively on real training observations. The runtime smoother has **25 minutes** of history at this native cadence. Fixed ML parameters match the controlled suite: 150 iterations, 15 leaves, L2=3, seed 42; at most 200,000 seeded pooled valid training rows. The reserved validation partition is unused because parameters are fixed. This is a temporal univariate adaptation, not DCRNN reproduction or a graph-model leaderboard claim, and does not validate intersection-count forecasting. Plots show a fixed sensor's first 288 held-out origins; full test metrics use all sensors and origins.

## Real-world-derived control

SUMO 1.27.1 runs the published RESCO Cologne1 network and OD trips, including real-derived topology and turning movements. Demand is taken directly from the scenario rather than replaced by Poisson arrivals. Tuning uses 07:00–07:30 (1,126 scheduled trips), seeds 1001/2002. Test uses the disjoint 07:30–08:00 period (889 scheduled trips per run), seeds 42/43/44. Four controllers share identical trip files, seeds, network, horizon, and transitions: **12 held-out runs**, plus 12 tuning runs.

The published eight-green-phase fixed controller uses 10/10/40/10/10/10/40/10 seconds. ATLAS's adaptive queue rule is generalized to eight phases with 12-second minimum and 60-second maximum. A density max-pressure variant compares incoming and downstream lanes, with minimum green, maximum green, and a 180-second starvation bound. It represents the recognized policy family; it is not a claim to reproduce a specific published implementation. ATLAS uses its existing constrained-search objective family generalized to the scenario, evaluates six predeclared pairs for phases 2/6, fixes other greens at 12 seconds, and caps the cycle including clearance at 200 seconds. Only tuning-period objectives choose the split. There are no pedestrians, so that objective term and pedestrian wait are explicitly unavailable.

Every policy has 3-second yellow and 2-second all-red clearance and legal published green states. Teleporting is disabled. Mean/median vehicle delay includes SUMO `timeLoss`, insertion/departure delay, unfinished inserted vehicles, and horizon-minus-scheduled-departure delay for vehicles never inserted. All 889 scheduled trips remain in the denominator. Completed-only travel time is labeled and accompanied by unfinished counts. Queues count stopped vehicles on local inbound lanes, excluding off-network backlog; approach fairness covers vehicles observed at the controlled lanes, not every possible OD origin. Stops are running-to-stopped transitions. Both limitations are explicit.

The held-out timing search **regresses** against fixed timing. The dashboard retains the negative reduction, every seed, selected candidates, and tuning objectives. Max-pressure performs better. Period shift, limited candidate capacity, fixed-cycle control, and this small network constrain transfer. This is simulated performance under published real-derived demand, not a field intervention or certification.

## Real footage systems and qualitative safety

Full production runs use all 4,260 actual UA-DETRAC frames encoded losslessly to FFV1; encoding occurs before timing and decoded pixels are checked. Timed processing includes initialization, detection/tracking, trajectory analytics, safety-engine invocation, SQLite writes, and JSON persistence in an isolated local evaluation runtime. Detector/tracker inference p50/p95/p99 is recorded separately. Another artifact records distinct detector-only and production tracker passes. No model cache restoration is timed as fresh inference.

Hardware: Intel i7-14700HX, 28 logical processors, 15.71 GiB RAM, Windows build 26200, Python 3.11.9, CPU inference at 640 pixels. RSS is sampled every 0.1 seconds; sequential runs retain allocator caches. Process CPU can exceed 100% because several cores are used; machine-capacity percentage divides by logical core count. This developer workstation is not an isolated performance host. These sequences permit more throughput than the original aerial profile's archived 19.5 sampled FPS; the model, resolution, footage, and sampling differ. GPU and live-camera transport remain unmeasured.

Safety runs on the real footage but correctly remains **gated off** without verified metric calibration. Generated event count is zero; this is not evidence of zero conflicts or correct classification. TTC/PET/minimum separation distributions and replay examples are unavailable rather than invented from pixel-space geometry. `real_safety_qualitative.json` explicitly records this limitation. No practical labeled and calibrated conflict dataset was integrated. Supervised real-world near-miss accuracy remains unmeasured; synthetic AUROC/F1 stays in the controlled section.

## Artifacts and validity

`BenchmarkArtifact` schema version 1.0 requires type, provenance, dataset/version, model, date, hardware, split, seed (nullable), metrics, and scope; methodology and per-sequence/per-seed results accompany them. Nonfinite numbers are rejected; unavailable quantities are null. JSON writes are atomic. Normalized copies of original artifacts preserve original dates and unknown hardware fields rather than manufacturing new measurements. `/api/benchmarks` reads actual files; `/api/benchmarks/{name}` exposes the complete JSON with validated names. CSV exports carry scope. Plots are standalone PNG files.

Primary threats: selected three-camera subset; mirror transformations/license ambiguity; merged classes; no human conflict labels or road calibration; highway-to-intersection target mismatch; missing sensor records; limited pooled training sample; only three simulation test seeds; one junction and one held-out demand period; generalized control adapters; throughput affected by developer-machine load. Repeating deterministic model scoring verifies reproducibility, not independent scientific replication. None of these results establishes field safety benefits, city-scale capacity, or broad domain generalization.

Ordinary CI uses tiny archive/annotation fixtures, analytic matching/split/score tests, schema/API tests, and browser fixtures loaded from committed measured JSON. No large datasets are downloaded. Full evaluations are manual commands; optional TrackEval tests skip when evaluation extras are absent. The original controlled suite and all prior functionality remain available.
