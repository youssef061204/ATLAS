# Run the experimental increment

Native development:

```powershell
.venv/Scripts/python -m pip install -e '.[dev,cities]'
.venv/Scripts/python scripts/restore_city_scenarios.py
.venv/Scripts/python -m uvicorn atlas.api:app --host 127.0.0.1 --port 8000
# In frontend:
npm run dev
```

Open `/cities`, `/studio`, `/benchmarks`, `/pilot`; original `/workspace`, analytics, safety, forecasting and signal laboratory remain. Set `ATLAS_OPERATOR_KEY` only on the Python server to enable local operational writes; configure CORS for the actual frontend origin. The local studio accepts the operator key in memory to submit two real queued simulations and replay their completed results. Leave it unset for read-only use. No key is bundled as `NEXT_PUBLIC_*`.

Docker's API image installs the city/SUMO dependencies and restores the small packaged corridor inputs before running as the existing non-root user. `docker compose up --build -d` remains the local entry point. The public Vercel project and existing portfolio remain preserved; this increment does not imply a new production deployment.

Read-only public presentation:

```powershell
$env:NEXT_PUBLIC_DEMO_MODE='true'
$env:NEXT_PUBLIC_API_URL=''
npm run build
npm run start
```

This serves genuine recorded aggregate source checks and completed simulation artifacts. It does not contact official cameras live or run new SUMO/CV jobs. Preparing or deploying a newer build must keep that distinction visible.

Linux research reproduction:

```powershell
docker build -f docker/city-evaluation.Dockerfile -t atlas-city-study .
docker run --rm --mount "type=bind,source=$PWD,target=/study" --entrypoint python atlas-city-study scripts/restore_city_scenarios.py
docker run --rm --mount "type=bind,source=$PWD,target=/study" atlas-city-study --city all --seeds 20 --seed-start 20001 --output data/five-city-reproduction.json
```

For RESCO, first use the existing licensed-data preparation script for Cologne1 and Ingolstadt1, then run `scripts/benchmark_v2_transfer.py --seeds 20 --start 34001 --output data/transfer-reproduction.json` inside the research image. Preserve source checksums and original frozen source. Do not overwrite historical published artifacts.

To generate a **new** OSM snapshot, run `scripts/generate_city_network.py --city all --download`; this changes network inputs and requires a distinct benchmark version. Image checks require authorized official network access; registration/restrictions remain source-specific. Linux reproduction is authoritative; Windows SUMO drift remains documented.
