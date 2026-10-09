# ATLAS 3.0 measured results and reproduction

Original artifacts remain unchanged. Numerical claims below come from separately recorded actual executions; generated documentation does not rerun a benchmark. Hardware, hashes, exact protocols and every comparator are linked in [VERIFIED_ENGINEERING_METRICS.md](VERIFIED_ENGINEERING_METRICS.md).

## Forecasting advancement

| Horizon | Original ATLAS ML MAE | New graph-assisted classical MAE | Matched temporal MLP MAE | Directional GNN MAE |
|---|---:|---:|---:|---:|
| 5 min | 2.489726 | 2.438439 | 2.415974 | **2.344069** |
| 15 min | 3.214339 | 3.122171 | 3.046921 | **2.975469** |
| 30 min | Not measured in original artifact | 3.765762 | 3.640538 | **3.546621** |

All values are mph on the same 207-sensor METR-LA chronology and valid-target masks. The GNN wins validation against the matched MLP at all three horizons. Its 3,617 parameters use one learned local/upstream/downstream message layer. Best epoch is selected on validation, with twelve fixed maximum epochs, seed 42 and four CPU threads. The neural training set contains more sampled targets than the classical fit: this is not an equal-training-budget comparison against boosting.

Paired calendar-day block bootstrap on 24 shared test days (20,000 draws): five-minute reduction versus original **5.8503% [5.5867, 6.1281]%**; fifteen-minute **7.4314% [6.8942, 8.0608]%**. Graph versus matched local MLP improvements are **2.9762%, 2.3451%, 2.5798%** at 5/15/30 minutes. Temporal dependence, one training seed and reuse of the historical ATLAS holdout limit these findings; independent prospective replication remains outstanding.

All-207-sensor GNN forward-only p95 is approximately **0.218 / 0.235 / 0.259 ms**. It excludes HTTP, input preparation, checksum verification and browser rendering. A separate measured classical native-service profile includes context/checkpoints/features/cache: cold **1,433.7 ms**, warm p95 **10.685 ms** over 100 same-input calls, excluding HTTP. Neither result is a sustained production SLA.

Reproduction after legitimate METR-LA preparation:

```sh
python scripts/evaluate_forecast_v3.py
python scripts/forecast_v3_paired_analysis.py
python scripts/prepare_forecast_runtime.py
python scripts/profile_forecast_runtime.py
python scripts/evaluate_graph_forecast.py
python scripts/analyze_graph_forecast.py
```

Read the frozen [classical protocol](forecast-v3-protocol.json) and [neural protocol](graph-forecast-protocol.json) first. Exact training/evaluation source copies are retained under `artifacts/cities/research-source`; later runtime changes do not silently replace them. Dataset/model downloads and checkpoints remain outside source control. Full classical preview is losslessly compressed; the UI preview uses the first four source-ordered sensors and first 288 test origins, not selected favorable examples.

## Perception findings

YOLO26n is not promoted: mAP@50 **0.894132** versus original **0.898212**, IDF1 **0.792172** versus **0.792770**, with lower recall and HOTA. Identity switches improve from **151 to 97** and fragmentation from **445 to 313**. Detector/tracker-only CPU throughput is **34.074 versus 27.934 FPS** in separate non-isolated host runs. It is not the original complete pipeline's **29.419 FPS**, and does not establish a repeated end-to-end speedup.

Virtual-line evaluation compares existing continuous tracked video with independent UA-DETRAC annotations: **18** predefined camera/gate/direction cases, **272 crossing events**, weighted absolute count error **0.085648 per 2.4-second bin**, including many empty bins. Crossings are not unique vehicles or surveyed turning movements.

Robustness checks execute **1,500** inferences: the first 100 held-out frames from each of three cameras under five fixed conditions. Brightness, blur, half-resolution restoration and JPEG degradation are controlled modifications of real imagery, not natural rain/night/snow validation. The easier 300-frame prefix has a different baseline than the complete 4,260-frame detector benchmark; its high mAP cannot replace the original whole-subset score.

```sh
python scripts/evaluate_cv_v3.py
python scripts/publish_cv_v3.py
python scripts/evaluate_visual_flow.py
python scripts/evaluate_perception_robustness.py
```

The operator geometry and continuous-motion queue candidate are tested, but **no independently annotated lane mapping or physical queue MAE is available**.

## Connected twin and control

The Toronto Bay/Queen golden path processes a real official snapshot and uses explicit unvalidated residence/OD assumptions. The unchanged seed-21001 matched case yields frozen MPC **26.178 s** and prototype **21.009 s** mean simulated delay. The current replay adds actual SUMO positions; its previous result and exact source are separately preserved. This single conditional case does not establish city traffic savings.

The frozen five-city nominal study has 400 runs; two RESCO transfer networks add 160. It retains prototype regressions against original MPC in Cologne and all five city corridors. Ingolstadt improvement over the frozen MPC largely uses max-pressure fallback and does not beat max-pressure. No tuning on final seeds is represented as new held-out evidence.

A new sixteen-run diagnostic removes sensor information uniformly from all adaptive policies, unlike the old excluded outage diagnostic. Actual outage and lane-slowdown results and all eight ablations remain visible. They do not establish universal robustness: outage performance and some ablations worsen. Source snapshots, weather and incident listings are not simulator-ground-truth measurements.

```sh
python scripts/restore_city_scenarios.py
python scripts/prepare_intelligence_demo.py
python scripts/evaluate_v2_resilience.py
python scripts/verify_city_intelligence.py
```

Run SUMO research inside the documented Linux image with version-pinned input files. `verify_city_intelligence.py` requires an authenticated native worker via `ATLAS_API_URL` and `ATLAS_OPERATOR_KEY`; it does not print the key. It processes at most two nearest eligible official cameras per city, refuses zero motor demand, and records successful and failed one-time 120-second smoke attempts without retaining images. These diagnostic seeds are not a held-out controller-performance cohort.

## Verification and deployment boundaries

Python verification includes all original tests plus geometry, causal features, neural messages, authorization, durable recovery/cancellation and independent historic-count consistency. Frontend checks include lint, types, formatting, production build, actual native jobs and public replay. Automated accessibility scans cover five primary areas on desktop and mobile; they do not replace manual accessibility or human usability studies.

The native smoke container has separately verified completed-result persistence after an actual restart and cancellation of an actual running simulation. Interrupted work is retained as interrupted, never automatically replayed. Current recovery assumes one API process owns the operations database. Distributed queue/rate-limit guarantees and load SLA remain unverified.

Fresh five-city native checks processed seven additional camera snapshots: Toronto, London and Austin completed paired conditional simulations; two sampled cameras each in Seattle and Calgary had zero detected motor vehicles and were not simulated. Every outcome is retained in `city-intelligence-smoke.json`. No undisclosed default demand was substituted. Including earlier checks, eighteen distinct sampled cameras have actual processed observations; this does not verify the other 2,825 discovered catalog entries.

The increment's current test counts are generated from the actual local JUnit report in [verified metrics](VERIFIED_ENGINEERING_METRICS.md). Production remote commits/deployments require their own final verification. New functionality must not be described as publicly deployed merely because the earlier ATLAS production URL loads.
