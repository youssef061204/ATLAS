# ATLAS 5 measured results

This engineering release preserves ATLAS 4 and all stronger historical benchmarks. **Zero independently validated city twins; zero observed field benefits; the experimental portfolio is not promoted.** Public Vercel serves genuine precomputed processing and simulation outputs. The private native worker has actual SUMO verification; public remote execution remains disabled.

## Five-city calibration

These are historical demand-profile reconstruction errors, **not simulated-state accuracy**. Whole observation dates split calibration, validation and final rows. The ATLAS 4 archive was already evaluated, so this is regression evidence rather than a new blinded cohort. Unknown channels receive no prediction. Source count accuracy, physical queues, speed and travel-time errors remain unavailable.

| City | Source bins | Final paired rows | Coverage | Count MAE / RMSE, vehicles per native bin | Flow MAE, equivalent veh/hour | GEH < 5 |
| --- | --- | --- | --- | --- | --- | --- |
| toronto | 832 | 112 | 40.0% | 73.989 / 90.027 | 295.955 | 42.0% |
| london | 204 | 36 | 100.0% | 481.103 / 584.698 | 481.103 | 33.3% |
| seattle | 24,857 | 4522 | 100.0% | 22.540 / 30.650 | 90.158 | 68.7% |
| austin | 7,970 | 1299 | 100.0% | 56.052 / 78.733 | 224.208 | 41.7% |
| calgary | 18,816 | 3360 | 100.0% | 15.204 / 29.614 | 60.815 | 84.7% |

Weighted nonnegative OD inversion rejects rank-deficient or unverified mappings. The production archive supplies no verified network incidence matrix; thus an OD solution is not invented. Arrival profiles use exposure-weighted Poisson shrinkage chosen on validation only; this is an explicit statistical assumption.

Official follow-up resolved 23 current Seattle street segments through COMPKEY, with zero missing keys. Current segment extent is not an exact historical counter/lane location. Toronto's official intersection register, Austin's radar sensor registry and Calgary's CalTRACS metadata are retained. Austin radar is also historical/discontinued. Whitehall count point 27663 supplies 240 actual directional hourly manual surveys across ten irregular dates. Its separate 7/1/2-date study estimates 48 final counts at MAE 353.208 veh/hour, normalized MAE 68.83%, and 0% GEH below 5: **unsuccessful**. Final uncertainty is unavailable with two dates. No sparse annual observations are presented as a current stream.

## City forecasting and transfer

Causal history ratios, local-time features where timezone is verified, validation-selected ridge/boosting, drift fallback and validation conformal intervals. Strict leave-one-city-out fitting, candidate selection and interval calibration use four source cities; target labels and target normalization statistics used: **0**. These historical final partitions were already evaluated in ATLAS 4. No model is promoted using these outcomes.

| City | Local MAE / persistence | Local reduction | Zero-shot MAE / persistence | Zero-shot reduction | Zero-shot 90% coverage / width / proper interval score |
| --- | --- | --- | --- | --- | --- |
| toronto | 28.509 / 28.509 | 0.00% | 26.197 / 28.509 | 8.11% | 100.0% / 284.43 / 284.43 |
| london | 33.387 / 37.444 | 10.83% | 35.374 / 37.444 | 5.53% | 88.9% / 413.19 / 459.04 |
| seattle | 14.137 / 16.236 | 12.93% | 15.035 / 16.236 | 7.40% | 87.1% / 87.12 / 101.95 |
| austin | 26.377 / 30.803 | 14.37% | 54.976 / 30.803 | -78.48% | 77.4% / 229.61 / 366.80 |
| calgary | 12.362 / 13.600 | 9.11% | 12.659 / 13.600 | 6.92% | 89.4% / 86.89 / 96.31 |

Errors are vehicles per each source's native count interval, not comparable physical queue errors. London local persistence regression is repaired in this study; Calgary zero-shot improves, but **Austin zero-shot worsens materially**. Toronto local abstains to persistence. Prior Seattle/Austin/Calgary ATLAS 4 local models remain stronger and preserved. Geographic-message ablations remain explicitly proximity models; no directed surveyed sensor graph exists. Independent multimodal contribution and few-shot transfer are blocked/not established.

## Robust control: new paired SUMO cohort

Development: 150 episodes; validation: 300; final: **2,100**. Final seeds 55301–55310, five city networks, low/nominal/high demand, lane closure, sensor outage and bursty demand shift, seven controllers. A threshold/hysteresis/dwell selector uses current measured inbound/downstream occupancy, frozen before final runs, never a final-outcome oracle. Paired route/network inputs and source initial states are verified; **300 cached/original pairs have identical measured outcomes**.

| Baseline | Mean paired delay reduction | 95% city/seed cluster interval |
| --- | --- | --- |
| fixed | 13.95% | 12.41 to 15.54% |
| max_pressure | 7.36% | 5.28 to 9.59% |
| original_mpc | -2.33% | -3.53 to -1.12% |
| cached_original | -2.33% | -3.53 to -1.12% |
| actuated | 5.75% | 3.16 to 8.48% |
| cooperative_q | -4.53% | -7.24 to -1.80% |

Positive reductions favor the portfolio. Overall cached/original MPC and cooperative Q beat the new selector. Seattle high improves 8.54% vs max-pressure and Calgary nominal 21.20%, but Toronto low regresses 2.94% on average and **28.75% in seed 55307**. That exceeds the predeclared 20% worst-episode allowance; **promotion fails and production policy is unchanged**. Zero modeled signal-safety violations occur in all 2,550 new episodes. This does not certify field actuation, pedestrian safety or municipal compliance.

Every per-seed delay p95, throughput, unfinished trips, queue, stops, travel time, phase switches, modeled emissions, decision latency, worker RSS and wall time is published. Pedestrian/transit/spillback measurements remain null where unsupported; emissions are SUMO estimates with explicit telemetry coverage. Bootstrap blocks retain all six scenarios per city/seed. Original 1,800 episodes remain untouched. The queue surrogate remains retired because it lost to persistence across all five cities.

## Repeated complete computer-vision pipeline

Three counterbalanced repetitions per tracker, complete 1,130-frame MVI_40701, CPU YOLO11n/640/confidence 0.25. Outer wall timing includes fresh model/tracker startup, decode, inference, analytics, forecasting, SQLite and JSON persistence. No physical calibration is supplied; safety inference remains gated. Shared Intel i7 host load and observed eight PyTorch threads are recorded.

| Tracker | Complete aggregate FPS | Median wall time | Complete-sequence IDF1 / HOTA |
| --- | --- | --- | --- |
| bytetrack.yaml | 18.33 | 60.78 s | 0.739 / 0.635 |
| botsort.yaml | 15.06 | 74.83 s | 0.756 / 0.663 |

BoT-SORT's median complete wall time is 23.1% higher. Single-sequence IDF1 improves from 0.739 to 0.756 and count MAE from 2.122 to 1.945 vehicles. ByteTrack remains production. These scores do not replace the historical three-sequence 0.793/0.808 IDF1 results. The measured 18.33 FPS narrow repeat workload is slower than historical 29.4 FPS; hardware load, cold-start and sequence differences prevent attributing this as a controlled code regression or speedup. City CV labels, lane assignment and physical queue ground truth remain absent.

## Product, workers and reproducibility

Bundled licensed fonts and reserved asynchronous loading space reduce the maximum observed local CLS from 0.567 to 0.024 across 30 matched city/view/viewport cases, with zero automated accessibility violations, page errors, failed responses or horizontal overflow. A separate mobile-throttled Lighthouse sample scores performance 97, accessibility 100, best practices 100 and SEO 100. Each case has one local sample; this does not establish a statistical speedup or field Core Web Vitals. Lighthouse LCP is slightly higher after the change. Human participants remain zero. The actual 36-second walkthrough and five source-hashed screenshots show current application output.

The public journey connects official city observations, twin-validation matrix and exact count/demand series, corridor replay, the ATLAS 5 six-case comparison, and authentic ten-seed pilot exports. Native prediction results and transfer regressions are visible in each city's calibration view. Linked replay uses actual five-second SUMO snapshots; maps are not camera trajectories. Every model/result has scope and provenance.

Confidence-aware fusion rejects incompatible units, unmapped footprints, stale/future measurements and low coverage. It avoids double-counting overlapping cameras and quarantines camera/detector disagreement. Its variance is conditional on supplied measurement models; no calibrated uncertainty or empirical city-fusion gain is claimed without coeval sources.

The authenticated native API has durable SQLite jobs/quotas, one owned child per bounded paired experiment, account isolation, cancellation, timeout, aggregate RSS monitoring, source/parameter experiment IDs, progress, heartbeat and hashed results. Actual native SUMO verifies the lifecycle. It is **disabled publicly**. External hosting requires TLS, secret provisioning, kernel CPU/PID/disk limits, retention, observability and budget approval; it is not presented as a deployment sandbox. No new paid service was introduced; incremental hosted-worker spend is $0, existing account charges and local electricity are unmeasured. [Worker architecture](execution-v5.md).

`python scripts/verify_v5_evidence.py` checks all 75 lossless episode bundles, sources, final pairing, frozen protocols, regressions, CV repeats and native-worker provenance without restricted datasets. The ATLAS 4 measured frontend source is preserved in `ux-measured-source.zip`, allowing frontend evolution without relabeling old browser measurements. [Usability protocol](usability-v5-protocol.md): **zero participants**, no invented human results. Current automated verification and production provenance are recorded separately at release.

## Supervised municipal pilot readiness

Ready for a technical research demonstration and agency data-readiness discussion. **Not ready for an operational benefit claim or unattended signal actuation.** A defensible shadow pilot needs verified historical/current lane and detector correspondence, contemporaneous timing/conflict/pedestrian surveys, independent count and dynamic-state holdouts, source-specific uncertainty, camera permissions, a reviewed security/cost envelope, agency-approved oversight and a prospective causal evaluation. Level 2 remains blocked for all five cities; Level 3 is unmeasured. No task passing substitutes for those observations.

Evidence: [`artifacts/cities/v5`](../artifacts/cities/v5), frozen protocols and scripts; historical [ATLAS 4 results](atlas-4-results.md), [real-world evaluation](real-world-evaluation.md) and [Cologne control results](signal-control-results.md).
