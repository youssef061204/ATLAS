# ATLAS 6.0 — continuous-video validation plan

Status: complete-video baseline implemented and measured; physical-fidelity acceptance **fails**.
The application synchronizes all 11,220 NGSIM frames, actual CV tracks and native SUMO output.
Independent comparisons expose under-reconstruction; the second source supports only a qualified
471/720-second holdout. CityFlow's four-video experiment regresses after association and is not
promoted. A bounded native Caltrans HLS trial verifies continuous transport, but its nighttime
detector produces no tracks; live tracking quality remains unvalidated. No live worker runs on
the public deployment. [Actual results and remaining gates](reality-v6-results.md).
This plan supersedes any snapshot-led ATLAS 6 proposal. ATLAS 5 evidence remains historical,
unchanged, and separately scoped. All acquisition and processing must cost $0.

## First release gate: a complete observed-video experiment

Before CityFlowV2, live integration, platform expansion, or new portfolio claims, produce one
working NGSIM Lankershim experiment containing **all** of the following:

1. Acquire a complete raw moving-vehicle video from the [official FHWA video collection](https://data.transportation.gov/d/uv3e-y54k), its independent video-transcribed trajectories, roadway geometry, and signal timing. Validate archive CRC, file hashes, decodability, duration, frame continuity, time bases, coordinate units, and camera coverage. Keep source files local and ignored; record per-asset licensing and attribution. A trajectory CSV, processed annotation video, sample frame, or video URL alone does not satisfy this gate.
2. Process every consecutive decodable frame of that complete video through the actual ATLAS detector/tracker. Preserve frame timestamps, boxes, IDs, trajectory samples, inference timings, frame failures, and source/model/config hashes. Report lost frames and incomplete decoding as failures. Distinguish image-plane motion from calibrated physical speed.
3. Reconstruct the corresponding road segment/intersection in actual SUMO using documented geometry, lanes, connectivity, and signal plans. Establish camera-to-road calibration and source-clock alignment from development data. Disclose missing support files and uncertain map/signal parameters; do not silently invent them.
4. Run a physically simulated reconstruction with frozen parameters. Declare observed boundary arrivals and signal schedules as conditioning inputs when used. Never use held-out interior positions, speeds, queues, or exit times to steer the simulation. An observed-trajectory animation or `moveToXY` replay may be an explicitly labelled visualization, but cannot establish simulation fidelity.
5. Quantitatively compare ATLAS perception and the free-running reconstruction against independent observations. Publish errors, coverage, unmatched vehicles, sample sizes, uncertainty, and known annotation limitations—even if performance is poor.
6. Demonstrate synchronized video and the corresponding SUMO output in the application, with functioning play/pause/scrub controls and observed-versus-simulated metrics. A dashboard or adapter without this experiment is incomplete.

Use the first observation period for development/calibration/validation and reserve the second
period for final temporal holdout. Freeze exact source-clock windows, camera coverage, whole-track
exclusion rules, parameters, metric definitions, and acceptance criteria before scoring the holdout.
Vehicle identities must be scoped to source sequence; IDs can recur across recordings. Exclude
tracks crossing partition boundaries. Do not count repeated frames or same-day cameras as
independent days. Any data inspection or protocol change after evaluation must be logged.

## Measurement and provenance contract

Measure only quantities supported by observations and defensible calibration:

| Quantity | Independent comparison and required qualification |
| --- | --- |
| Tracking | Matched source vehicle trajectories; ID consistency, fragmentation, position error, precision/recall and match coverage. Pixel box metrics require independent boxes; do not manufacture boxes from point labels. |
| Speed and trajectories | Source-space matched trajectories and physical speed errors after camera calibration, with calibration residuals and unit/time checks. |
| Turns and lanes | Source movement/lane annotations, explicit lane convention and intersection mapping; report confusion and coverage. |
| Counts | Independent crossing events in the same camera region, direction, line, and interval; MAE, bias, totals and missed/duplicate crossings. |
| Travel time | Matched complete traversals between fixed observation boundaries, with censoring/unmatched counts and MAE/bias. |
| Queues | Observed slow/stopped vehicle occupancy on a declared lane segment; threshold, persistence, spatial extent and occlusion limits; queue-length error and discharge profiles. |
| Signal cycles | Independently documented controller timing or explicitly audited video signal observations, clock alignment and missing phases; cycle-by-cycle queue discharge and timing error. |
| Physical SUMO fidelity | Held-out speed, travel time, counts, queues and discharge at common times/locations; state which boundary inputs are observed. Aggregate agreement alone is insufficient. |

Keep perception accuracy separate from simulation accuracy. Report both reconstruction driven by
independent boundary observations and the end-to-end CV-driven result where possible; otherwise
do not imply perception errors were included in the simulator evaluation. Quantify performance
on this footage rather than transferring UA-DETRAC FPS/accuracy claims to NGSIM.

Source annotations have their own position errors and occasional inconsistencies. FHWA's
metadata warns that some loop turning counts overestimate movements. Treat such sources as
qualified observations, not perfect labels. Source clock offsets must be reconciled explicitly.
Counterfactual controller improvements remain **simulation experiments**, never field intervention
benefits. Do not optimize controllers on the final reconstruction holdout.

## Primary interface

- **Left:** real continuous video, ATLAS boxes and tracked IDs, calibrated measurements with provenance and confidence/availability. Source annotations are a separate optional overlay.
- **Right:** corresponding SUMO vehicles, road lanes and signal states, driven by the same source time. Label free-running physical reconstruction separately from observed trajectory replay.
- **Bottom:** observed-versus-simulated charts, errors and coverage, controller comparisons, shared timeline, play/pause, scrubbing and synchronization status. Buffering or seeking must not silently drift the two panels.

Historical footage is labelled **HISTORICAL VIDEO / PRECOMPUTED PROCESSING** in public replay.
Only active authorized stream decoding/inference may be labelled **LIVE PROCESSING**. Public
Vercel playback serves verified precomputed artifacts; native long-running CV/SUMO remain in
the real backend. Do not imply the browser or Vercel executes unavailable infrastructure.

## Second gate: CityFlowV2

After the complete NGSIM milestone, obtain CityFlowV2 through its official authorized distribution
and review its research/license/access conditions. Record any actual access boundary. Evaluate
continuous multi-camera tracking, camera calibration where available, identity association,
cross-camera travel time, and generalization with camera/sequence-disjoint splits. Do not claim
physical speed or signal validation when that dataset lacks the necessary calibration or labels.

## Third gate: authorized live continuous video

Investigate Traffic Cam Archive's free live viewing and original upstream providers. Free viewing
does not by itself authorize automated processing, recording, or redistribution. For each candidate,
record the actual provider terms, automation permission, protocol and codec, measured duration,
timestamp/frame progression, cadence, availability, and permitted retention. Accept HLS, MJPEG,
RTSP or equivalent genuinely moving video; reject periodic JPEG snapshots and slideshow wrappers.
Never buy archive access, use a paid API, bypass authentication, disable TLS verification, or
present an unverified stream as integrated live video.

For an authorized source, implement continuous bounded decoding, persistent tracking, rolling
counts/speeds/queues where calibrated, disconnect/reconnect with identity reset, stale/frozen-frame
detection, health telemetry, latency/backpressure, and an explicitly authorized expiring local buffer.
Test actual stream behavior as well as failure recovery. If no legal free source qualifies, publish
that limitation and retain historical video as the verified experience.

## Release gate

Run meaningful backend, CV/data-integrity, synchronization, browser, accessibility, responsive,
lint/type/format/build/startup and evidence checks. Verify that old ATLAS 5 artifacts still pass their
existing integrity checks. Publish reproducible derived results and actual application captures;
do not commit raw restricted datasets, model caches, secrets or temporary buffers. Update README,
technical documentation, resume bullets and the existing portfolio using only newly verified metrics.
Push without rewriting history to the existing ATLAS and YoussefElsokkary repositories, deploy
their existing free Vercel projects, and verify production URLs and remote commit SHAs. A blocked
dataset or stream, incomplete experiment, or failed physical model must remain explicitly visible.
