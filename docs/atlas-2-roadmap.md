# ATLAS 2.0 engineering roadmap

The reference is commit `4f760bb0b9ee6dc017c9ed2c57a705be5c4891ec`. Historical artifacts, `control.py`, `signal_lab.py`, and the frozen MPC profile remain immutable. New experiments use separate modules, protocols, and output directories. Historical results are not new reproductions.

## Baseline and execution paths

55 Python tests pass at the start of this upgrade. The native path is FastAPI → bounded process jobs → YOLO/ByteTrack → SQLite/results → Next.js analytics and replay. SUMO research runs are offline scripts, not traffic hardware integration. Public Vercel serves genuine saved outputs; it cannot execute the Python/CV/SUMO worker. The old controller is one junction, with causal EWMA arrivals and a fluid beam search. Its Ingolstadt transfer failure remains published. Native Windows SUMO reproducibility drift remains a limitation.

## Working increments

1. Preserve baseline; validate existing checks and source hashes. Establish this roadmap and an evidence ledger.
2. Five official camera adapters, validated metadata, bounded image retrieval, timestamp semantics, rate limits, provenance, health and aggregate-only snapshot perception. No invented speeds or trajectories from stills.
3. Small OSM corridor onboarding, pinned downloads and checksums, SUMO conversion and independent assumed demand, source attribution, explicit calibration gaps. Camera discovery does not establish traffic demand.
4. Separate deterministic safety gate, risk-aware local control, capacity normalization, cooperative graph messages, audited fallback. Compare against unchanged original MPC and pressure under paired demand. Freeze protocol before evaluation; avoid tuning on final results.
5. Causal state estimation, probabilistic forecasts, incidents, authorized simulated priority, multi-objective and pilot calculations. Validate each execution boundary and disclose unsupported outcomes.
6. City operations, network views, comparison replay, decision inspection and pilot export backed by saved source/experiment/API records. Preserve original routes and public demo.
7. Failure recovery, deployment profiles, load/performance checks, regression suite and a 20-item status report.

## Evaluation scope

Start with small actual executions, then scale. Five-city OSM smoke simulations are exploratory until independently calibrated. A publication study targets ≥20 unseen paired seeds per city/regime and is a distinct expensive deliverable. Do not describe a smaller smoke run as commercial validation. Do not compare homemade algorithmic baselines to proprietary SCOOT/SCATS as authentic implementations. No deployment or hardware changes are required to test new local functionality.

The acceptance ledger in `docs/atlas-2-status.md` records complete, partial, blocked, or not-started status for all 20 upgrades with commands and evidence. Completion of a module does not imply acceptance of a city-scale research claim.
