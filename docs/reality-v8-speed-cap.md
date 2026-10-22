# ATLAS 8 CV birth-speed correction: experimental evidence

The frozen ATLAS 7 CV birth adapter estimates a speed from five consecutive detections, then additionally caps it using braking distance to the **end of the current SUMO edge**. That edge often continues through Main Street. An edge boundary is not itself a stop line, so the extra cap can request nearly zero speed for a vehicle observed moving near the junction. The [ATLAS 8 opt-in policy](../backend/atlas/birth_speed_v8.py) requests the observed CV speed, bounded by the existing 15.65 m/s vehicle maximum, and leaves SUMO insertion, car-following, signal and collision rules enabled. The [one-factor runner](../scripts/ablate_edge_end_speed_cap_v8.py) changes only `departSpeed` for affected frozen CV births; a [verifier](../scripts/verify_birth_speed_v8.py) checks every route field and source hash. The ATLAS 7 generator, network, signal approximation, random seed, demand identities and published baselines remain unchanged.

Both scoring windows were already exposed. These are controlled regression measurements, **not a fresh physical holdout**. The trial never uses future reference states for admission or motion. Reference trajectories are used only after the native run to score the same timestamped observations. The CV births themselves are conditioned on observed interior video states, so these numbers do not describe an unconditioned outer-boundary forecast.

| Complete camera-4 video, 30–300 s development | Frozen ATLAS 7 | ATLAS 8 opt-in |
| --- | ---: | ---: |
| Independently annotated scoring states | 1,441 | 1,441 |
| Native presence | 69.47% | 68.98% |
| Reference states within 4 m | 18.74% | 19.57% |
| Uncapped matched position MAE | 11.75 m | 9.92 m |
| Matched speed MAE | 2.61 m/s | 2.40 m/s |
| Instantaneous count MAE | 1.478 vehicles | 1.352 vehicles |
| Completed trips / 321 requests | 314 | 310 |

The full-edge policy changed 88 of 321 initial speed requests. On the identical **374 northbound states**, position MAE fell from **18.99 to 11.97 m**, but native presence fell from **63.37% to 62.03%**. A separate [south-approach-only ablation](../artifacts/reality/v8/south-edge-speed-cap-ablation-development.json) changed 27 `S_in` births: northbound MAE fell to **12.19 m**, presence remained **62.03%**, and the 1,067 southbound scoring states were essentially unchanged. The all-edge development run sampled 316 versus 308 distinct native IDs in the 1 Hz FCD. These losses and the four fewer completed trips are material regressions, even though the conditional position and count errors improved. [Full development artifact](../artifacts/reality/v8/edge-end-speed-cap-ablation-development.json).

The same policy was run across the **entire 1,122 s video** with all 1,272 frozen CV birth requests, then scored on the already exposed **600–1000 s known regression**:

| Known regression, identical 2,670 reference states | Frozen ATLAS 7 | ATLAS 8 opt-in |
| --- | ---: | ---: |
| Native presence | 54.57% | 54.98% |
| Reference states within 4 m | 12.66% | 14.49% |
| Uncapped matched position MAE | 13.64 m | 11.80 m |
| Matched speed MAE | 2.98 m/s | 2.65 m/s |
| Instantaneous count MAE | 2.860 vehicles | 2.858 vehicles |
| Completed trips / 1,272 requests | 1,262 | 1,265 |

This run changed 363 initial speed requests. The [known-regression artifact](../artifacts/reality/v8/edge-end-speed-cap-known-regression.json) records the same-denominator direction splits, network/route hashes, source hashes, native-run counters and exact FCD hashes. The full-window native FCD SHA-256 hashes are `ebdd4319eaf85ff1322c712ecab4e363dfe9ffe68b7cda46fe44b5f2ff82d4db` (frozen baseline) and `d2064c26abcded341ca33bf371beec43ec2545f78ded4e6a7a7abc479ab16a49` (opt-in). The trial and baseline SUMO logs contain no warning, error, collision or teleport messages. The 1 Hz FCD sampled 1,261 versus 1,240 unique IDs; that sample count is **not an exact insertion count**, since a short-lived trip can complete between samples. Requested and completed trips are reported separately.

The correction is **experimental only**. It improves position error on two previously exposed windows, but the development run loses presence and completions, the known regression still has only 14.49% of reference states within 4 m, Main Street lamp state and turn-bay geometry remain unverified, and no new independent footage/reference cohort has been scored. It does **not** pass the [physical acceptance protocol](reality-v7-protocol.json), prove a real-world signal-control benefit, or justify replacing the public replay. The opt-in can be reproduced from the verified local source data with `scripts/ablate_edge_end_speed_cap_v8.py`, `scripts/ablate_south_edge_speed_cap_v8.py`, and `scripts/ablate_edge_end_speed_cap_known_v8.py`; these scripts refuse to overwrite completed artifacts. Run `scripts/verify_birth_speed_v8.py` against local native outputs, or `scripts/verify_reality_v8_artifacts.py` for the publishable artifact consistency checks. Seven focused policy tests pass.
