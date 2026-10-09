# Evidence-backed resume bullet candidates

Generated from actual artifacts. Choose claims appropriate to the role; include the qualifications when discussing the work. Projections and unmeasured targets are excluded.

## Software engineering

- Built a five-city official traffic ingestion and simulation platform, discovering 2,843 camera records and processing 18 verified snapshot observations across 18 sampled cameras.
  - Evidence: source-health + toronto-intelligence; HTTPS allowlists, bounded reads/retries, privacy-preserving aggregate retention. Catalog count is metadata scale; only sampled image access was verified. Hardware: Intel(R) Core(TM) i7-14700HX; source checks are one-time observations, not uptime measurements.

## Machine learning engineering

- Developed validation-selected graph context traffic forecasting, reducing five-minute METR-LA MAE by 2.06% over the original ATLAS ML baseline (2.438 vs 2.490 mph) across 207 sensors.
  - Experiment: metr-la-graph-context-v3-01; chronological 70/10/20, 1,247,252 valid targets, same original test period. CPU: Intel(R) Core(TM) i7-14700HX, four threads; all-sensor p95 1.06 ms. Static graph-assisted classical model, not a neural GNN; independent external replication outstanding.
- Implemented a 3,617-parameter directional graph neural traffic forecaster, reducing five-minute METR-LA MAE by 5.85% over the original ML baseline (2.344 vs 2.490 mph) across 207 sensors.
  - Experiment: metr-la-learned-graph-v3-01; 1,247,252 valid held-out targets, best epoch selected on validation; paired day-block 95% interval [5.59, 6.13]%. Four CPU threads; forward-only p95 0.218 ms. Highway domain, one training seed, shared historical test period; external replication and calibrated intervals remain pending.

## Computer vision engineering

- Built a CPU traffic video pipeline achieving 0.898 mAP@50 and 0.793 IDF1 across 4,260 annotated UA-DETRAC frames.
  - Experiments: real_detection, real_tracking, real_video_pipeline; three official test sequences; Intel(R) Core(TM) i7-14700HX, 29.4 complete-pipeline FPS. Vehicle aggregate class; calibrated road speeds and visual queues not validated.

## Applied AI / research engineering

- Validated traffic controllers in 560 paired SUMO runs across seven modeled networks, improving Ingolstadt mean delay by 35.29% versus the frozen ATLAS MPC over 20 seeds.
  - Experiments: five-city-nominal + transfer, predeclared seeds 20001–20020 / 34001–34020; Linux SUMO 1.27.1. Ingolstadt improvement primarily uses a topology-triggered max-pressure fallback; no superiority over max-pressure. Cologne and five city corridors regressed versus the frozen MPC. Not field validation.

## Systems and performance engineering

- Engineered an end-to-end CPU traffic pipeline processing 4,260 real annotated frames at 29.4 FPS, including tracking, analytics and SQLite/JSON persistence.
  - Experiment: real_video_pipeline; Intel(R) Core(TM) i7-14700HX, peak RSS 634.8 MiB. Lossless video preparation excluded; developer machine, no isolated host. New controller profile does not support a speedup claim.

Full numerical evidence, hardware, comparator context, limitations and source hashes: [VERIFIED_ENGINEERING_METRICS.md](VERIFIED_ENGINEERING_METRICS.md).
