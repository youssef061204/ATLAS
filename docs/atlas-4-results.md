# ATLAS 4.0 measured results

Generated from recorded experiment artifacts by `python scripts/generate_v4_metrics.py`. This does not execute benchmarks. Original results and the [3.0 ledger](atlas-3-status.md) remain preserved. No new candidate is automatically promoted.

## Official city counts and chronological forecasting

Five official adapters acquired **52,679 real historical count bins**. Separate observation dates define training, validation and test periods. Three contiguous causal bins are required; missing bins remain missing. [Source provenance and licensing](atlas-4-data.md) · [Frozen protocol](city-forecast-v4-protocol.json) · [Actual results](../artifacts/cities/v4/city-forecast.json).

| City | Validation-selected model | Test examples | Native interval | Test MAE | Persistence MAE | MAE reduction | 90% interval coverage |
|---|---|---:|---|---:|---:|---:|---:|
| Toronto | geographic_message_network | 265 | 15 min | 29.066 | 28.509 | -1.95% | 90.19% |
| London | temporal_mlp | 27 | 60 min | 39.430 | 37.444 | -5.30% | 100.00% |
| Seattle | temporal_mlp | 4,498 | 15 min | 13.161 | 16.236 | +18.94% | 89.97% |
| Austin | temporal_mlp | 1,245 | 15 min | 26.048 | 30.803 | +15.44% | 91.73% |
| Calgary | histogram_gradient_boosting | 3,339 | 15 min | 11.183 | 13.600 | +17.77% | 89.91% |

Toronto and London test regressions are retained even though their models won validation. The geographic message network is a learned one-hop proximity model, not a surveyed directed road graph. Its contribution is compared with a matched local MLP in every city; it is not consistently superior. Austin's discontinued vision counters are not independently audited count truth. London has few irregular hourly survey observations. Marginal conformal intervals use validation residuals; temporal shift can violate exchangeability.

## Strict four-city zero-shot transfer

Every rotation trains on only the other four cities, including normalization and epoch selection. No target-city calibration is substituted for zero-shot inference.

| Held-out city | Test MAE | Persistence MAE | MAE reduction | Target-city fit examples |
|---|---:|---:|---:|---:|
| Toronto | 28.465 | 28.509 | +0.15% | 0 |
| London | 31.829 | 37.444 | +15.00% | 0 |
| Seattle | 14.246 | 16.236 | +12.26% | 0 |
| Austin | 34.456 | 30.803 | -11.86% | 0 |
| Calgary | 42.552 | 13.600 | -212.88% | 0 |

Transfer failures prevent an operational promotion. Different source years and native intervals do not become simultaneous multimodal observations. All five SUMO twins remain exploratory: surveyed approaches, historical geometry, field queue/travel-time truth and municipal timing are not independently validated.

## Continuous-video perception

All three candidates process output for the same 4,260 complete UA-DETRAC frames. ByteTrack reproduces the preserved historical IDF1/HOTA exactly. Adaptive skipped frames hold the previous measured boxes; they are not newly detected trajectories. [Registered protocol](cv-v4-protocol.json) · [Actual per-camera/gate/cost records](../artifacts/cities/v4/perception.json).

| Candidate | IDF1 | HOTA | ID switches | Fragmentation | Visible-count MAE | Process CPU seconds | Actual inference frames |
|---|---:|---:|---:|---:|---:|---:|---:|
| bytetrack_full | 0.792770 | 0.639741 | 151 | 445 | 1.302113 | 1436.875 | 4,260 |
| botsort_full | 0.807740 | 0.665311 | 129 | 399 | 1.298826 | 2577.875 | 4,260 |
| bytetrack_adaptive | 0.792909 | 0.629674 | 115 | 396 | 1.251878 | 1480.062 | 3,247 |

BoT-SORT improves tracking accuracy but increases measured process CPU cost. Adaptive sampling reduces inference calls but does not establish lower CPU cost and reduces HOTA. No default changes. These are tracker-stage experiments on the reused historical holdout; the original 29.4 FPS refers to the unchanged complete ByteTrack pipeline. Ultralytics overrides the requested initial four-thread setting during CPU device setup; a separate same-path runtime probe observes eight threads. Wall timings share the development host and do not establish an isolated speedup. No independently annotated physical queue, natural-weather or five-city tracking score is inferred.

## Controller and simulator research

[Planner profile](../artifacts/cities/v4/controller-profile.json), [actual simulator equivalence](../artifacts/cities/v4/subscription-equivalence.json), frozen development/validation/final cohorts and cooperative-Q results are separate from city field validation. Exact historical traffic outcomes and modeled safety are preserved. Final cohort conclusions belong to the completed control report.

On 1,000 matched synthetic decision snapshots, 1,000 actions agree. Planner p95 falls from 2.084 to 0.585 ms (71.95% lower). This excludes SUMO and HTTP; shared-process RSS does not establish memory savings.

Completed **1,800 deterministic held-out SUMO episodes**: five cities, three generated-demand regimes, twenty paired seeds, six controllers. Cached MPC preserves original traffic outcomes. Reductions below are means of paired seed percentages, with 95% bootstrap intervals; positive means less delay. These are exploratory, uncalibrated OSM corridors, not field savings.

### Nominal generated demand

| City | Cached/original delay | Reduction vs fixed (95% CI) | Reduction vs max-pressure (95% CI) |
|---|---:|---:|---:|
| Toronto | 26.917 s | +17.81% [+13.39, +21.50] | +6.59% [+1.75, +10.82] |
| London | 8.202 s | +30.64% [+28.80, +32.44] | +11.90% [+10.31, +13.56] |
| Seattle | 38.834 s | +18.48% [+16.23, +20.57] | +8.44% [+5.54, +11.19] |
| Austin | 47.116 s | +20.45% [+18.74, +22.03] | +6.76% [+4.85, +8.50] |
| Calgary | 18.408 s | +1.03% [-5.65, +7.82] | +11.71% [+5.88, +17.54] |

### Low generated demand

| City | Cached/original delay | Reduction vs fixed (95% CI) | Reduction vs max-pressure (95% CI) |
|---|---:|---:|---:|
| Toronto | 25.426 s | +29.17% [+25.97, +32.13] | +0.47% [-6.55, +7.07] |
| London | 7.573 s | +33.24% [+29.20, +37.03] | +22.05% [+18.20, +25.78] |
| Seattle | 33.239 s | +30.62% [+27.91, +33.28] | +20.16% [+16.15, +24.20] |
| Austin | 42.173 s | +29.30% [+27.71, +30.76] | +12.18% [+9.43, +14.61] |
| Calgary | 14.059 s | +28.67% [+25.55, +31.84] | +31.97% [+28.92, +35.02] |

### High generated demand

| City | Cached/original delay | Reduction vs fixed (95% CI) | Reduction vs max-pressure (95% CI) |
|---|---:|---:|---:|
| Toronto | 37.824 s | +6.06% [+2.20, +10.01] | -2.49% [-8.14, +3.22] |
| London | 12.942 s | +21.62% [+19.89, +23.40] | +7.98% [+5.09, +10.78] |
| Seattle | 58.672 s | +6.44% [+4.28, +8.54] | -4.24% [-8.15, -0.25] |
| Austin | 65.885 s | +9.23% [+7.35, +11.18] | +2.53% [+0.52, +4.49] |
| Calgary | 19.195 s | +22.12% [+18.59, +25.23] | +37.76% [+35.29, +39.92] |

High-demand Seattle loses to max-pressure; high-demand Toronto and low-demand Toronto have inconclusive pressure comparisons. Nominal Calgary's fixed-time confidence interval crosses zero. No universal superiority is claimed.

### Cooperative multi-agent zero-shot research

A shared tabular cooperative policy trains on four cities per rotation, then freezes before testing the fifth. Forty 300-second training episodes and one hundred nominal held-out episodes execute actual SUMO; every action passes the independent modeled safety gate. Unseen states fall back to max-pressure. This is an experimental cooperative Q learner, not a deep graph MARL policy.

| Held-out city | Delay | Reduction vs fixed | Reduction vs max-pressure | Reduction vs original (95% CI) |
|---|---:|---:|---:|---:|
| Toronto | 29.342 s | +10.47% | -1.91% | -9.78% [-13.57, -5.76] |
| London | 9.473 s | +19.96% | -1.94% | -15.72% [-19.27, -12.08] |
| Seattle | 35.906 s | +24.61% | +15.43% | +7.23% [+3.07, +11.51] |
| Austin | 42.647 s | +28.01% | +15.59% | +9.26% [+6.82, +11.77] |
| Calgary | 14.733 s | +20.89% | +29.34% | +17.90% [+11.36, +24.28] |

Toronto and London regress; no policy promotion. Learned-policy low/high robustness is unmeasured. All one hundred modeled safety counts are zero; this is not a physical certification. [Complete comparisons](../artifacts/cities/v4/controller-results.json) and lossless archives include every run. One Austin high-demand actuated attempt encountered non-finite geographic replay coordinates; an isolated serialization-only recovery reran the unchanged seed and frozen physics, retained finite metrics, and explicitly marked two coordinates unavailable. [Failure and recovery record](../artifacts/cities/v4/controller-telemetry-recovery.json).


The vehicle-subscription audit identifies 1 held-out episode with physically invalid integrated CO2/fuel values and potentially contaminated stop events (Austin, high-demand actuated seed 43002). Frozen raw values remain unchanged. These quantities and affected aggregates are unsupported; no emissions/stop benefit is inferred. Native execution exposes unavailable values and retains the invalid originals for audit. Delay/completion come from separate SUMO trip outputs. [Quality ledger](../artifacts/cities/v4/measurement-quality.json) · [Actual native recovery verification](../artifacts/cities/v4/telemetry-native-verification.json).

## Actual browser and native API verification

Local production browser evidence includes 12 matched route/viewport observations and 38 automated accessibility scans. Timing is one sample per route, not a field Core Web Vitals or human task study. [Raw observations](../artifacts/cities/v4/ux-performance.json).

| Landing viewport | Before transferred bytes | After transferred bytes | Observed reduction |
|---|---:|---:|---:|
| 1440 px | 1,098,906 | 653,475 | 40.53% |
| 390 px | 1,075,677 | 626,156 | 41.79% |

Authenticated native count inference reproduces each first chronological test prediction; 250 repeated warm HTTP requests cover all five frozen models. Unauthorized requests are rejected and snapshot stock is refused as measured flow. This is a warm local latency check, not concurrent service throughput. [Actual profiles](../artifacts/cities/v4/city-runtime-profile.json).

The learned five-second observed-policy queue surrogate loses to queue persistence in all five held-out cities. It is not used to replace SUMO truth or rank unsupported counterfactual plans. [All surrogate failures](../artifacts/cities/v4/surrogate.json).
