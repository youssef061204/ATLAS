# Public demo deployment

**Verified production:** https://atlas-mu-murex.vercel.app (Vercel project `atlas`, repository `youssef061204/ATLAS`, build root `frontend`). Four browser smoke tests passed against this unauthenticated HTTPS origin on 2026-10-05. The team's generated deployment URLs remain protected; the production alias is public.

The production Next.js frontend runs on Vercel. The Python/FastAPI backend, CV process pool, SQLite persistence, native SUMO evaluations, and long-running inference remain in the local/Docker architecture. No publicly hosted Python backend was found during deployment preparation.

## Precomputed public experience

The Vercel project has production/preview build environment variables `NEXT_PUBLIC_DEMO_MODE=true` and `NEXT_PUBLIC_API_URL=''`; matching runtime configuration is in `frontend/vercel.json`. Configure these in the project before its first build, since public Next.js variables are compiled into browser bundles. The Next.js read-only API adapter serves same-origin replay assets; it does not start Python or expose credentials. Visitors can replay actual detections and trajectories, inspect analytics, switch real forecasting horizons, compare recorded simulation policies, and read the complete real benchmark artifacts. New uploads, calibration changes, and alternative simulation settings require the local backend and are explicitly disabled in the public experience.

The video is an attributed, annotated presentation derived from Mixkit #1755 and its genuine ATLAS CV output. It is a time-lapse engineering sample, not the UA-DETRAC evaluation footage. Detection/tracking scores come from the separately measured UA-DETRAC subset. Forecasts come from real METR-LA holdout. The interactive optimization recording is controlled synthetic simulation; the real-world-derived RESCO benchmark and its negative ATLAS result appear separately on Benchmarks. Unverified physical calibration gates real safety claims.

`npm run build` prepares assets from committed compressed outputs only when demo mode is enabled. Replay frame/trajectory decimation reduces bandwidth without changing model configuration or benchmark values. Raw datasets, source stock video, checkpoints, credentials, and model caches are excluded from Git.

## Reproduce and verify

Use project root `frontend`, Node.js 24, and allow source files outside the root so the build can read repository benchmark artifacts. The public environment variables in `vercel.json` are configuration, not secrets. HTTPS and same-origin API requests avoid a local backend and cross-origin dependencies.

```sh
cd frontend
NEXT_PUBLIC_DEMO_MODE=true NEXT_PUBLIC_API_URL='' npm run build
NEXT_PUBLIC_DEMO_MODE=true NEXT_PUBLIC_API_URL='' npm start
ATLAS_PUBLIC_DEMO=1 ATLAS_WEB_URL=https://YOUR_PRODUCTION_DOMAIN npm test -- --grep public-demo
```

On PowerShell set environment variables with `$env:NAME='value'`. Production browser tests cover immediate replay, WebGL twin, real benchmark links, forecasting, simulation playback, prohibited mutation responses, JavaScript errors, and mobile overflow.

Full processing remains available with `docker compose up --build -d`. If a Python backend is hosted later, use a durable container service with persistent storage and workers, configure the HTTPS API origin, and permit the deployed frontend origin in backend CORS. Do not move expensive processing into the small replay adapter.
