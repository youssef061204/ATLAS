# Architecture

ATLAS uses one Python service and one Next.js interface. This keeps the numerical pipeline inspectable and the clean install small enough for a reviewer. Go, PostgreSQL, Redis, and Kafka would add deployment obligations without demonstrated value at the measured local workload; they are not included as portfolio keywords.

## Runtime boundaries

| Boundary | Responsibility | Persistence / protocol |
|---|---|---|
| Next.js / React | synchronized source playback, 3D reconstruction, charts, camera setup, paired replay | typed REST, progress SSE |
| FastAPI | validate uploads/configuration, bound queue, expose results/health/metrics | OpenAPI; loopback default |
| Process pool | one model/tracker instance per job, decode and sample source, isolate model failures | filesystem + SQLite status snapshots |
| Perception | COCO street-level or VisDrone aerial weights; selectable ByteTrack / BoT-SORT | confidence, class, box, persistent ID |
| Trajectories | foot-point projection, least-squares motion on a recent time window | indexed per-track time series |
| Analytics / safety | unique IDs, dwell/stops, region occupancy/exits; TTC, closest approach, PET proxy | frame metrics and reviewable event records |
| Simulation | reproducible arrivals, car following, signal clearance, pedestrian service | saved frames and policy objectives |
| Experiments | isolated synthetic splits, official metric evaluation, actual systems load | JSON and flattened CSV |

## Data flow

1. Upload bytes under a UUID filename. Check extension, size, decodability, frame rate, and duration.
2. Register intersection, camera, and video; enqueue a bounded processing job.
3. The worker initializes its own detector/tracker, decodes every source frame, and samples according to camera settings.
4. Each tracked bottom-center point is transformed when calibration exists. Least-squares velocity uses source timestamps rather than assuming a fixed inference rate.
5. Region membership yields intersection entries/exits and inbound stopped queues. Traffic metrics remain tied to sampled source time.
6. Verified road-plane calibration enables physical safety screens. A missing calibration produces an explicit disabled state.
7. Persist results transactionally and replace the JSON result file atomically. The API streams stage changes and current observation metrics while processing.
8. The browser uses video time as the playback clock; frame, overlay, tracks, and inspector all derive from that time.
9. Signal experiments use identical demand and separate tuning seeds. Completed and unfinished demand contribute to objectives.

## Schema and concurrency

Two versioned SQL migrations define intersections, cameras/configuration, videos, frame metadata, tracks, trajectory points, traffic metrics, safety events, forecasts, and experiment runs. Video/intersection and video/time indexes serve the primary access paths. Calibration and regions live in validated camera JSON; experiment payloads retain their configuration and seed provenance.

SQLite runs with WAL, foreign keys, connection-local transactions, and a 30-second busy timeout. Each process opens its own connection. The API exposes at most eight queued/running inference jobs, with one worker by default. This is a bounded local queue, not a durable distributed broker. Interrupted jobs become failed on API startup and can be reprocessed. CLI initialization does not interrupt active API jobs. CLI inference bypasses the API resource queue, so avoid additional inference commands when the machine is already saturated. Cache bootstrap checks both source and compressed-result checksums and reuses an existing matching cached record.

`/metrics` exports request histograms/counters, active jobs, and actual worker-persisted frame/latency/memory measurements. The collector reads persisted worker measurements, avoiding the false zero counts that process-local Prometheus registries would produce. Per-video telemetry is limited to the latest 100 videos. Inference quantiles describe detector and tracker execution; they exclude queue waiting and model loading. Pipeline wall time includes initialization and numerical work; initial result latency is separately recorded.

## Scaling boundary

Identifiers and APIs support multiple intersections. Runtime capacity is bounded by CPU/GPU inference and complete-result transfer. A long run currently keeps trajectory history and sampled frames in memory and returns a complete result to the browser; it is not a tested city-scale deployment. The measured load artifacts expose the local API's saturation. A later distributed worker queue, object store, relational backend, and time-window result endpoint should be motivated by measured multi-camera workloads.
