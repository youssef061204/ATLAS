# ATLAS 4.0 evidence-backed resume candidates

Retain the earlier [role bullets](RESUME_BULLETS.md) and historical Cologne, highway-GNN and complete CPU pipeline results. New city-count and CV experiments have distinct domains and costs.

## Software engineering

- Built provenance-aware traffic-count ingestion across five official city sources, preserving 52,679 historical measurement bins with digest-checked caching, bounded retrieval, source-local timestamps and missing-data safeguards.
  - Evidence: data-index.json and five compressed licensed aggregate archives; one-time source checks, not continuous availability.

## Machine learning engineering

- Reduced held-out Seattle 15-minute count forecasting MAE by 18.94% versus persistence (13.161 versus 16.236 vehicles/bin) on 4,498 chronological test examples using validation-selected temporal mlp.
  - Evidence: city-forecast.json; observational source counts, single training seed, not city queue accuracy or realized traffic savings.
- Reduced held-out Austin 15-minute count forecasting MAE by 15.44% versus persistence (26.048 versus 30.803 vehicles/bin) on 1,245 chronological test examples using validation-selected temporal mlp.
  - Evidence: city-forecast.json; observational source counts, single training seed, not city queue accuracy or realized traffic savings.
- Reduced held-out Calgary 15-minute count forecasting MAE by 17.77% versus persistence (11.183 versus 13.600 vehicles/bin) on 3,339 chronological test examples using validation-selected histogram gradient boosting.
  - Evidence: city-forecast.json; observational source counts, single training seed, not city queue accuracy or realized traffic savings.

## Computer vision engineering

- Evaluated BoT-SORT against ByteTrack on 4,260 independently annotated traffic frames, improving IDF1 from 0.793 to 0.808 and HOTA from 0.640 to 0.665, with identity switches falling from 151 to 129.
  - Evidence: perception.json; three reused UA-DETRAC sequences; higher CPU cost, optional candidate only; no new full-pipeline FPS claim.

- Vectorized and cached safety-gated MPC beam search, preserving 1,000/1,000 matched actions while reducing observed planner p95 from 2.084 to 0.585 ms (71.95%) on synthetic eight-phase snapshots.
  - Evidence: controller-profile.json; actual artifact values, shared development host; excludes simulator/API and does not imply better traffic outcomes.

- Built 5 frozen four-city cooperative-control rotations and evaluated 100 zero-shot SUMO episodes; nominal delay reductions versus frozen MPC: Seattle 7.23%, Austin 9.26%, Calgary 17.90%; Toronto, London regressed.
  - Evidence: controller-results.json; 20 paired seeds per city, generated demand, no automatic promotion or municipal savings claim.

## Applied AI / research

- Implemented reproducible chronological five-city forecasting and five strict leave-one-city-out rotations, with validation-selected models, test-day paired uncertainty, interval coverage, drift flags and preserved transfer regressions.
  - Evidence: city-forecast.json; highway benchmarks remain separate, no automatic promotion.

## Infrastructure / performance

- Built authenticated city-count inference with checksum-pinned local checkpoints, weights-only neural loading, causal cadence/domain validation, bounded caches and explicit shadow-versus-persistence monitoring.
  - Evidence: city-runtime-profile.json and runtime behavior tests; same-input local HTTP probes are not a sustained production SLA.
