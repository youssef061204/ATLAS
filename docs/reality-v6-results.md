# ATLAS 6: continuous-video experiment and measured failures

This is a working video-driven baseline, **not an accepted physical twin**. The [revised plan](reality-v6-implementation-plan.md) requires continuous footage and independent observations. Snapshot feeds do not satisfy it. [Public video and synchronized SUMO](https://atlas-mu-murex.vercel.app/reality) · [machine-readable evidence](../artifacts/reality/v6/manifest.json) · [preserved ATLAS 5 results](atlas-5-results.md).

## What actually ran

- Downloaded the complete FHWA Lankershim Camera 4 raw recording, independent trajectories, actual CAD/GIS roadway support and controller RSM timing. The 449,073,152-byte AVI passes official archive CRC and SHA-256, independently decodes **11,220 consecutive frames at 10 Hz**, and has no consecutive pixel-identical frames. Its actual duration is **18:42**, longer than its nominal filename interval. Source-clock metadata starts at 08:28 on June 16, 2005.
- Ran the actual ATLAS production `process_video` pipeline over every frame: frozen YOLOv8n-VisDrone, 960-pixel input, confidence 0.15, ByteTrack, CPU inference. Complete-run timing is recorded in the manifest, not inferred from playback cadence or transferred from UA-DETRAC. Track IDs include fragmentation and are not unique vehicle counts.
- Estimated camera registration from 12 development-only footprint centers, using nine for fitting and three for a spatial check. Check RMSE is **0.758 m on three points in one frame**, not whole-camera or temporal accuracy. Static image features align raw and rectified views. Raw CV input contains no ground-truth ID overlays. U.S. survey feet and local international feet are handled separately.
- Built and ran native **SUMO 1.27.1** with development-derived road geometry and turn probabilities, an approximate two-stage RSM schedule and frozen physical parameters. The public replay uses **207 CV-derived boundary arrivals**; no held-out ground-truth arrivals, interior positions, speeds, exit times or `moveToXY` commands drive that run. Safe insertion and subsequent motion use SUMO physics. A separate observation-conditioned boundary diagnostic is explicitly distinct.
- Processed all **8,109 consecutive frames across four complete CityFlowV2 S02 videos**. Candidate tracklets use frozen COCO YOLO11n/ByteTrack, actual crop embeddings and ground-truth-blind offline association. Original videos, crops, embeddings and research artifacts remain local; only aggregate evaluation is published.

## Quantitative evidence

Development recording validation is **600–1000 s**, after the development/calibration windows. The independent reference is FHWA's video-transcribed NGSIM trajectory data, not ATLAS predictions. Source annotation uncertainty, camera occlusion, roof parallax and approximate road coverage remain limitations.

| Measurement | Actual result | Interpretation |
| --- | --- | --- |
| CV point-trajectory IDF1 | **0.685** | 4 m physical-center gate; 376 reference IDs, 431 predicted track IDs, 400 sampled seconds. Not conventional box IDF1 or comparable to UA-DETRAC. |
| Matched physical position MAE | **1.213 m** | Conditional on the 4 m gate; 1,620 matches of 2,670 reference observations (**60.7% coverage**). |
| Matched CV speed MAE | **0.781 m/s** | 1,536 speed pairs; misses are excluded, so read alongside 60.7% reference coverage. |
| CV instantaneous visible-count MAE | **2.213 vehicles** | Fixed physical region, not crossing-flow accuracy. |
| End-to-end CV-driven SUMO count MAE | **5.603 vehicles** | 400 one-second comparisons; bias −5.603, substantial under-reconstruction. |
| Southbound stopped-queue count MAE | **0.640 vehicles** | Observed peak 8 versus simulated 3. Below 0.5 m/s for three consecutive 1 Hz samples; fixed upstream region, not queue-tail length in metres. |
| NB crossing counts at two fixed lines | **137 / 22 and 143 / 22 observed/simulated** | Missed/fragmented CV boundary tracks propagate into simulation. |
| SB crossing counts at the same lines | **220 / 46 and 232 / 46** | Same 400-second interval; 30-second bins include the final partial bin. |
| NB / SB travel-time distribution distance | **1.402 / 1.758 s Wasserstein** | Unpaired complete-traversal distributions, not individual-vehicle travel-time MAE. Cohorts differ: 136/22 NB and 215/45 SB. |

The observation-conditioned boundary diagnostic also fails: matched speed MAE **3.295 m/s**, mean position error **16.608 m**, 80.1% matched-observation coverage. It has more informative boundary inputs than the end-to-end CV run and must not be substituted for it.

### Qualified temporal holdout: incomplete original source

The second official AVI passes ZIP CRC but is **internally truncated**: 261,284,939 actual bytes versus 419,190,690 RIFF-declared bytes; 6,538 decodable of 10,480 declared frames. Faithful downloading does not make its source complete. The production decoder now rejects this file before inference and rejects early decoder termination before persisting a successful result.

The frozen quality guard uses only the first **6,510 exact source frames**, extracted to a lossless FFV1 clip with decoded pixel hashes checked against the original. This is explicitly a **derived partial clip**, never a repaired or complete original recording. Frozen parameters and static camera registration use no held-out trajectory labels. Only then are independent labels loaded to score **[180, 651) seconds: 471 of 720 planned seconds (65.4%)**. The remaining 249 seconds are missing/guarded, not silently dropped from the denominator. The [qualified holdout artifact](../artifacts/reality/v6/holdout-prefix-results.json) contains the actual errors, totals, source chain and coverage; this diagnostic fails physical fidelity.

This is aggregate temporal validation. Whole-track partition helpers are tested, but these published aggregate experiments do **not** establish a vehicle-disjoint identity holdout. The overlapping beginning of the second recording is excluded; repeated source IDs are scoped to recordings. No model, association threshold or controller was selected using these holdout outcomes.

The guarded rerun scores **8.278-vehicle visible-count MAE** and **0.648-vehicle stopped-queue MAE**; the observed queue peak is 7 versus simulated 0. At the first line, NB crossings are **215 observed / 46 simulated**, SB **314 / 79**. Unpaired travel-time distribution distances are **3.218 s** in both directions (201/41 NB and 305/79 SB complete traversals). These discrepancies reinforce failure; the incomplete 65.4% coverage cannot be presented as a successful full holdout.

### CityFlowV2 association failed

On the same **60,682 candidate boxes**, global annotation-scoped IDF1 falls from **0.260 before association to 0.220 after association** (−3.986 percentage points). The separate multi-camera-filtered cohort scores 0.221 and is not the same-detections ablation. **The association is not promoted.** This is one four-camera zero-shot transfer experiment, not the complete CityFlowV2 benchmark or a leaderboard result. Only vehicles passing multiple cameras are annotated; apparent false positives can include unannotated single-camera vehicles. Source skipped/stuck frames and approximate offsets prevent claims of perfect multicamera temporal synchronization. No surveyed physical speed, queue or signal validation is claimed for CityFlow.

## What remains unproven

The approximate geometry omits turn bays, a bus layby and midblock driveways. Source RSM timing is available, but exact observed lamp states and lane-level phase mappings are not independently decoded. Turning/lane accuracy, discharge curves, paired individual travel times, metric queue-tail length and a complete planned final holdout remain unvalidated. The tiny spatial calibration check does not remove these limitations. There are **zero accepted physical twins and zero measured field intervention benefits**.

No ATLAS 6 controller improvement is claimed. New controller optimization waits for acceptable reconstruction fidelity. ATLAS 5's frozen robustness portfolio still improves fixed/max-pressure on average but fails promotion against cached MPC/worst-case guards; the earlier Cologne/METR-LA/UA-DETRAC results retain their original scopes.

## Architecture and reproduction ($0)

Native Python/OpenCV/PyTorch decoding and tracking write timestamped predictions. Development-only geometry and CV boundary crossings generate native SUMO network/routes; independent observations are evaluated after inputs/output are frozen. The exporter packages the complete licensed web video, 19 timestamped CV/SUMO chunks, the actual native run and aggregate error series. The Next.js `/reality` view derives both panels from one video clock and provides real play/pause/scrubbing/speed controls. Native positions are sampled at 1 Hz and interpolated for display, not for evaluation; CV boxes follow all 10 Hz frames.

Vercel serves **historical video / precomputed actual processing**. It does not execute expensive inference, SUMO or persistent workers. A separate native Caltrans HLS trial decoded 1,740 consecutive frames over seven consecutive segments (25 Hz), with inference on every sixth frame, no sequence gaps/resets and deletion of every temporary segment. The nighttime detector produced **zero tracks**, so live tracking quality remains unvalidated. Earlier heavier stream settings exceeded the retention/backpressure limit and were rejected. See the [live-source review](reality-v6-live-sources.md). Restricted raw data, local models, caches and temporary files remain ignored. The NGSIM web-video adaptation carries the official collection's CC BY-SA 4.0 attribution/license. Source trajectory catalog CC BY-SA 3.0 and older RDE metadata language are disclosed; raw source tables and support archives are not redistributed. CityFlow is noncommercial research only and is never deployed as a production model/data service.

The complete primary NGSIM inference and CityFlow experiments were measured before the decoder-only integrity guard; their exact runtime sources are retained in `artifacts/cities/v5/cv-runtime-source.zip`. The guard changes no successful inference algorithm. All presentation frames are independently decoded again, and regression tests cover truncated containers and premature EOF. A redundant primary inference repeat was interrupted to limit CPU contention; its partial predictions are excluded from every published result. The qualified holdout-prefix run uses the guarded runtime. CPU timings are scoped to individual runs on a shared host and are not cross-workload speed comparisons.

With Python 3.11 and the pinned editable project plus `evaluation`, `cities`, `media` extras, run these from the repository root. Acquisition requires substantial free local storage and public dataset access; no paid credentials are used:

```powershell
python scripts/acquire_ngsim_v6.py
python scripts/acquire_video_v6.py --member "NGSIM Lankershim Videos/lankershim-camera4-0830am-0845am.avi"
python scripts/acquire_video_v6.py --member "NGSIM Lankershim Videos/lankershim-camera4-0830am-0845am-processed.avi"
python scripts/acquire_support_v6.py
python scripts/download_trajectories_v6.py
python scripts/inspect_ngsim_v6.py
python scripts/calibrate_ngsim_v6.py
python scripts/process_ngsim_video_v6.py
python scripts/evaluate_ngsim_cv_v6.py
python scripts/reconstruct_ngsim_v6.py
python scripts/cv_driven_ngsim_v6.py
python scripts/acquire_video_v6.py --member "NGSIM Lankershim Videos/lankershim-camera4-0845am-0900am.avi"
python scripts/prepare_holdout_prefix_v6.py
python scripts/process_ngsim_video_v6.py --sequence holdout-prefix
python scripts/evaluate_holdout_prefix_v6.py
python scripts/acquire_cityflow_v6.py --scene S02
python scripts/evaluate_cityflow_v6.py
python scripts/process_caltrans_live_v6.py --seconds 60
python scripts/publish_replay_v6.py
python scripts/verify_v6_evidence.py
```

The frozen protocols are [NGSIM](ngsim-v6-protocol.json), [qualified prefix](ngsim-v6-holdout-prefix-protocol.json) and [CityFlow](cityflow-v6-protocol.json). This release records failures rather than tuning them away after evaluation. Dataset/model downloads can change availability; per-member CRC, SHA-256 and exact frame checks prevent silent source substitution.
