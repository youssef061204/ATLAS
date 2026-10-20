# ATLAS 7 engineering checkpoints

The original checkpoint below is retained as an engineering record. Completed experiment outcomes supersede its pending items in [the ATLAS 7 results report](reality-v7-results.md). Publication is verified separately; this file is not a deployment-completion claim.
The existing ATLAS 6 production deployment and its source/evidence archives remain intact.

## Verified so far

- Preserved exact ATLAS 6 sources before changes. Historical artifact verification uses the measured source archive, rather than silently substituting later code.
- Compared eight detector/tracker configurations on consecutive development video; selected a frozen full-frame plus overlapping-crop aerial detector with ByteTrack. Larger aerial YOLO11s and higher resolution did not win. COCO YOLO11n produced no usable detections on this aerial development clip.
- Processed all 11,220 Lankershim frames through the production multiscale pipeline. Shared-host CPU throughput: **4.803 FPS**; no real-time claim. This accuracy configuration costs substantially more than the retained single-pass pipeline.
- On the identical known 600–1,000 s validation cohort, raw point IDF1 improves **0.68523 → 0.72589**, reference coverage **60.674% → 65.843%**, and CV visible-count MAE **2.2125 → 1.8775 vehicles**. Matched position MAE increases **1.2128 → 1.2359 m** and speed MAE **0.7808 → 0.8049 m/s**. These are fixed-region 1 Hz points with a 4 m gate, not bounding-box benchmark scores.
- Separately marked offline continuity/short-gap reconstruction reaches **0.74065 point IDF1**, **68.390% coverage**, and **1.705-vehicle CV count MAE**, including 89 inferred observations at the scoring cadence. Actual detector observations and inferred boxes remain distinct. The longer-gap development candidate was rejected.
- Completed a new 1,122 s native SUMO run with 1,272 CV birth admissions. Known validation count MAE is **2.79 vehicles**, queue MAE **0.72**. Initialization differs from the old boundary-only run: one interior observed pose per admitted track, followed by free-running simulation. Directional flow errors remain large; no physical acceptance or controller promotion.
- Packaged all 11,220 video-frame records, 19 synchronized replay chunks, native evidence and per-track lifespan/gap/source-ID metadata. Reuses the actual verified video transcode; it does not duplicate or fabricate video.
- Built a geographically grounded interactive Three.js scene with FHWA survey linework, a georeferenced historical orthophoto, original instanced vehicle meshes, modeled lights, camera presets, follow mode, calibration support and explicit illustrative context. Native front positions are converted to vehicle body centers using native lengths.
- Video playback, pause, exact frame stepping, camera/track inspection, mobile accessibility, missing-artifact behavior and both restored historical videos pass browser checks. Development screenshots have no runtime errors or failing responses. Software-rendering performance under concurrent CV load was poor; lower graphics cost and demand rendering while paused were implemented and need a new measured active-playback check.
- Python suite passed **199 tests** before three additional point-metric tests, which also pass. Frontend lint and types passed before the latest rendering optimization; rechecks are in progress. These are checkpoints, not final release counts.

## Reserved-test failure and annotation audit

The preregistered Lankershim temporal test is 1,020–1,120 s. Its whole-window raw point IDF1 is **0.12559 for ATLAS 6** and **0.15686 for the frozen ATLAS 7 candidate**; count MAE increases **4.53 → 4.55 vehicles**. The offline secondary reaches **0.17867**, with **4.68-vehicle count MAE**. These weak outcomes remain published.

No source reference identities are first observed after 1,019.9 s. The strict fresh-track test therefore has **zero eligible reference observations** and cannot estimate fresh-identity generalization. The scorer initially raised a zero-denominator error on that empty cohort. Its original exact sources are archived; a separate archived correction only adds null coverage and an explicit unestimable-cohort notice. Matching, region, cohort rules and models were unchanged.

A post-outcome source-coverage audit shows no new source track entries during the test tail. A separate image-only diagnostic finds less than half a pixel of sampled road-point movement relative to the calibration image. These diagnostics do not replace or improve the frozen scores. The interval does not provide an entry-complete independent-location benchmark.

## Independent data and remaining experiments

- All five first-recording Lankershim source videos have consistent RIFF/member headers. All five second-recording videos are internally truncated. Header consistency alone is never called full decoding verification.
- Two complete Peachtree recordings were downloaded and completely decoded with CRC/SHA checks: camera 5 (14,982 frames) and camera 1 (14,961). Camera 1 production inference is running; an earlier interrupted attempt produced no completed result and is not counted.
- Peachtree camera 1 image/world/time calibration is frozen using only the first 300 s. Three development image checks independently locate the raw-video offset at **four frames**. Two spatial check points give **0.7004 m RMSE**; 12 later development check points give **1.5364 m RMSE**. These are calibration diagnostics, not full-scene confidence bounds. The 600–900 s independent-location holdout and all three scoring cohorts are frozen before test outcomes.
- CityFlow S02's initial label-blind geometric ablation improves known-regression IDF1 **0.26012 → 0.26314** on identical detections. The old appearance-only regression to 0.220 remains preserved. S01 development and S03 held-out camera groups were acquired; actual full-video processing is running. New evaluation handles the 8 FPS source camera, source radial distortion, and explicitly separate annotation-padding ablations. No S03 ground-truth outcomes have been inspected.
- Live daytime processing, Peachtree physical reconstruction, forecasting suitability, final performance/media, full release verification, portfolio update, GitHub push and production deployment verification are outstanding. No current public live worker or accepted physical twin is claimed.

## Reproduction order

Use the frozen protocols and checksums in `docs/*v7*.json`. Run completed-video extraction, raw/secondary perception scoring, native reconstruction and `scripts/publish_replay_v7.py` in that order. `frontend/scripts/prepare-demo.mjs` checks each published replay asset against its manifest before preparing frontend assets. Raw datasets, weights, result caches and temporary buffers stay under ignored directories.

Do not overwrite measured artifacts, tune against held-out outcomes, weaken physical acceptance, or present an annotation-alignment/conditioning change as improved real-world physics.


## Completed experiments after the original checkpoint

All 49,979 newly processed frames across 13 videos completed. Peachtree frozen full-window point IDF1 is 0.49014 with 61.248% coverage; fresh identities score 0.45863. A pre-test cardinal-heading erratum leaves fit controls unchanged and worsens temporal-check RMSE to 2.1857 m; both sources are preserved. CityFlow S01 vehicle ReID development IDF1 is 0.51621, but frozen S03 raw IDF1 improves only 0.16354 to 0.16491. Filtering to linked identities regresses to 0.08541. No test outcome selected model changes.

Nine development-only SUMO behavior settings selected tau 0.7 s; a separate development-selected eager-insertion experiment retains all safety checks and reduces known-regression uncapped position MAE from 16.712 to 13.644 m. Coverage within 4 m rises 9.064% to 12.659%, but count MAE worsens 2.79 to 2.86. No physical gate is weakened and no physical twin is accepted. The public replay uses this final model with all regressions shown.

Actual daytime Taiwan MJPEG ingestion completed 258 frames with distinct compressed-JPEG hashes over 60.016 s, 142 with predicted tracks and five explicit reconnect resets. Source daytime pixels/car boxes were inspected; later follow-up images expired without inspection. Caltrans nighttime HLS completed six consecutive segments, 1,500 decoded/500 inference frames, 499 with tracks and no reset. Media was deleted. Archived telemetry is not current traffic; no live accuracy or unique-count claim.

The chronological video occupancy pilot reports all four fixed baselines at 1/3/5 minutes; ridge loses to the training mean at three minutes, and five-minute testing has just eight overlapping origins. Fifteen/thirty-minute evaluation and robust uncertainty are unsupported by source duration. Peachtree physical reconstruction and an independently accepted intersection remain unachieved; no new controller promotion follows.

Python: 213 tests pass. Source/metric verifiers for versions 3/4/5/6/7 pass. Frontend lint/types/production build pass, dependency audits report zero Python/frontend vulnerabilities, and a non-root resource-limited Docker backend starts with healthy API/network endpoints. The first full public browser run had 35 passes, six expected native-only skips and one keyboard-scroll accessibility failure, fixed; the final full rerun passes all 36 public tests with six native-only skips. All six distinct native flows also pass, including one retry after cold development compilation. Rendering/media and remote publication are verified separately in the release record.
