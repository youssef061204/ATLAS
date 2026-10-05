# API and deployment boundaries

Interactive generated OpenAPI is available at `/docs`, with schema JSON at `/openapi.json`.

| Method / route | Purpose |
|---|---|
| `GET /health` | API, DB connectivity, model/device/worker configuration |
| `GET /metrics` | Prometheus-compatible API and persisted worker telemetry |
| `GET/POST /api/intersections` | list/create sites |
| `GET/POST /api/videos` | list scoped recordings / multipart upload |
| `POST /api/demo` | enqueue the attributed local sample, reuse an existing current demo |
| `GET /api/videos/{id}` | stage, progress, error, source metadata, current observation metrics |
| `GET /api/videos/{id}/events-stream` | progress SSE snapshots with persisted update timestamps |
| `GET /api/videos/{id}/source` | original video, including range requests |
| `GET /api/videos/{id}/result` | complete JSON observations and provenance |
| `GET /api/videos/{id}/tracks` | track summaries |
| `GET /api/videos/{id}/metrics` | observation-time traffic series |
| `GET /api/videos/{id}/safety` | structured candidate events |
| `GET /api/videos/{id}/forecast` | source forecast or insufficient-history status |
| `GET/PUT /api/videos/{id}/camera` | camera configuration, calibration and regions |
| `POST /api/videos/{id}/reprocess` | rerun with updated camera configuration |
| `POST /api/simulations` | compare fixed, adaptive, and searched timing |
| `GET /api/simulations/{id}` | stored experiment |
| `GET /api/benchmarks` | generated machine-readable artifacts |
| `POST /api/streams` | explicitly enabled allowlisted stream capture |

Upload example:

```sh
curl -F 'file=@traffic.mp4' 'http://localhost:8000/api/videos?intersection_id=demo'
curl -H 'Content-Type: application/json' -d '{"seed":42,"duration":300,"demand":[0.38,0.12,0.32,0.10]}' http://localhost:8000/api/simulations
```

## Local safety controls

Uploads use UUID storage names, basename-only display names, an extension allowlist, bounded byte size and duration, and an OpenCV decode probe. Client filenames never choose a storage path. SQL uses parameterized values. Configuration forbids arbitrary tracker paths. Inference runs in worker processes, and no user input becomes a shell command. The pinned aerial weight is checksum-verified; custom administrator-selected weights must be trusted.

Streams are disabled by default. For a trusted local deployment, set `ATLAS_ALLOW_STREAMS=true` and `ATLAS_STREAM_HOSTS=camera.example` to allow credential-free HTTP/HTTPS/RTSP capture from that hostname. This path delegates network decoding to FFmpeg/OpenCV and is **not an Internet-facing SSRF sandbox**; redirects, nested playlists, decoder timeouts, and decoder resource consumption require stronger isolation before public deployment. It records a bounded clip before processing. Uploaded videos remain the tested primary input mode.

No public authentication or tenant authorization is implemented. Loopback bindings are intentional. Before sharing a deployment, add authentication, authorization, rate limits, decoder resource limits, stream isolation, TLS termination, storage lifecycle controls, and durable queue recovery appropriate to that environment. These are deployment requirements rather than hidden demo features.

All footage, tracks, and result files are retained locally. Stopping containers preserves the data volume. There is no automatic deletion policy. Operators own deletion and retention; never use live footage without appropriate rights. The system does not identify people, faces, or license plates.
