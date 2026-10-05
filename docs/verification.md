# Verification record

Performed locally on 2026-10-05. Windows host: Intel i7-14700HX, Python 3.11.9, Node.js 24.13.0, npm 11, Docker Desktop / Engine 29. Linux containers use Python 3.11 and Node.js 24. Results describe this environment and the recorded fixtures, not universal performance guarantees.

| Check | Result and evidence |
|---|---|
| Python tests | **34 passed**: calibrated geometry, pixel-unit preservation, timestamp regression, observed stops/queues, TTC/PET, deduplication, forecast history gate, no fabricated empty-video metrics, malformed/corrupt uploads, missing-model failure persistence, database failure, deterministic simulation, conservation, car-following gap, protected clearance, insertion-delay retention, cache/source checksum integrity, recovery isolation, and separated learning data |
| Python checks | Ruff lint, Ruff format, compileall, and pip dependency consistency passed |
| Frontend checks | ESLint, TypeScript, Prettier, and production Next.js build passed |
| Docker build/start | Backend wheel and production frontend images built from downloaded dependencies; Compose bootstrap completed, API became healthy, and web served the application |
| Native startup | `scripts/dev.py` launched both services, agent-browser loaded the landing page with no JavaScript errors, and Ctrl+C stopped the supervisor's own children |
| Browser integration | **8 passed against production Docker**: landing navigation, useful empty analytics, actual source seeking/overlay/selection/heatmap/camera modal, real policy optimization and paired seek, all data pages without exceptions, and mobile viewport overflow |
| Fresh HTTP inference | An actual MP4 upload completed under the default camera profile, then camera configuration/reprocessing ran YOLOv8n-VisDrone on all **480 frames** in the Linux worker |
| Replay/persistence | Fresh run had actual car/person tracks, 480 frame metrics, consistent relational track count, HTTP range replay, and persisted Prometheus worker frame measurements |
| Progress delivery | SSE delivered processing/terminal status updates from the fresh upload and reprocessing; timestamp-age quantiles are in `artifacts/live-verification.json`. These measure stage delivery, not frame-to-screen latency |
| Safety/history guards | Fresh unverified demo had no physical safety alerts and correctly returned insufficient forecast history |
| Detector integration | Real YOLO11n validation on COCO8's four images produced `artifacts/cv.json`; explicitly a smoke test |
| Tracking metric integration | Official TrackEval analytic identity-switch fixture passed; stored separately from field accuracy in `artifacts/tracking-metric-validation.json` |
| Learning experiments | Actual logistic/gradient boosting training and independent synthetic test scoring generated risk/forecast artifacts; thresholds/model selection did not use the test split |
| Control experiments | Actual constrained search and matched held-out replays generated three-seed simulation results, including off-network queue waiting |
| SUMO validation | Eclipse SUMO 1.27.1 ran matched seed-42 demand without warnings; baseline and portable-selected signal timing results are in `artifacts/sumo.json` |
| Systems benchmarks | Actual one/two-process CPU inference and 2,650 mixed API requests generated `streams.json` and `load.json` |
| Dependencies | `npm audit`: zero known advisories. `pip-audit 2.10.1` on the complete pinned `requirements.lock` snapshot: zero known advisories. Raw audit JSON accompanies the artifacts |
| Portfolio capture | Production full-page screenshots and a silent WebM walkthrough captured actual application operations |
| Public demo | **4 passed against the unauthenticated production Vercel URL**; all public navigation, real replay/twin, forecasts, recorded optimization, same-origin assets, real benchmark JSON, JavaScript errors, and desktop/mobile layout verified |

The Python TestClient currently emits an upstream Starlette deprecation notice recommending httpx2; existing tests pass with the pinned httpx dependency. It is a migration notice, not a failed check.

## Repeat the full integration

```sh
docker compose up --build -d
python scripts/verify_live.py
cd frontend
ATLAS_WEB_URL=http://127.0.0.1:3000 npm test
node scripts/record-demo.mjs
```

On Windows use `.venv/Scripts/python` and set `$env:ATLAS_WEB_URL='http://127.0.0.1:3000'` before `npm test`. `verify_live.py` uses the attributed demo, uploads it, performs two real processing runs, and writes a new verification artifact. First execution may download both detector checkpoints. It leaves its completed video available for inspection.

Backend/frontend check commands and benchmark reproduction commands are in [README](../README.md). [Hosted CI passed for publication commit 950a8a6](https://github.com/youssef061204/ATLAS/actions/runs/37359974257). The public production origin is [ATLAS](https://atlas-mu-murex.vercel.app); its four public smoke tests ran without Vercel authentication or a local API.

## Unverified or deliberately limited paths

- GPU acceleration, hardware webcams, live RTSP capture, and inference through a physical traffic camera were not measured. Stream import is disabled by default.
- UA-DETRAC detection/tracking/counts are measured on a predeclared three-sequence subset. Demo-specific accuracy, surveyed physical speed/queue error, real conflict precision, and exposure-based false alerts per hour remain unmeasured.
- Real highway-speed forecasting is measured on METR-LA with chronological holdout; intersection vehicle-count forecasting remains unvalidated on a long real recording.
- The default simulator does not implement turning movements, heterogeneous body dimensions, lane changes, or moving pedestrian bodies. The original SUMO cross-check is one seed with straight-through traffic; the added RESCO evaluation uses turning traffic and three held-out seeds but has no pedestrians.
- Public processing authentication, distributed job recovery, large-city capacity, and network spillback are outside this implementation. The public Vercel experience serves precomputed real outputs; full processing remains local/container based.
- npm/Python audits reflect known advisories at execution time. The Python audit covers the pinned snapshot, rather than operating-system packages or optional external model files.

These limits are visible in the product, technical report, and benchmark scopes; they are not replaced with invented scores.


## Real-data upgrade verification

Actual acquisition and full scoring completed for 4,260 UA-DETRAC test frames (three complete predeclared sequences), all 207 METR-LA sensors at 5/10/15-minute horizons, 12 tuning and 12 held-out RESCO Cologne1 SUMO runs, and fresh complete production processing of the same real footage. Official pycocotools and TrackEval produce the detection/tracking artifacts. Cached rescoring verifies original source/checkpoint/configuration checksums.

The 11 added Python tests cover local archive preparation, source tampering, annotation conversion, ignored-region matching, official perfect detection and tracking fixtures, identity fragmentation, causal imputation and split separation, mathematically valid forecast metrics, all-scheduled control denominators, phase constraints, artifact/schema/API validation, and skipping unprepared datasets without downloads. Optional metric tests skip in lightweight installations. Two added browser tests load committed measured artifacts, switch forecast horizons, retain the negative control result, and verify the absent-data state.

See [evaluation protocol](real-world-evaluation.md) for licenses, pinned revisions, exact reproducibility commands, measurement environment, and scientific limitations. Normal hosted CI uses fixtures and does not fetch large datasets; the full real-data evaluations were completed locally.
