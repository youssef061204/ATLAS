# Frozen signal-control results

Original historical result: ATLAS **66.45 s**, fixed **57.45 s**, max-pressure **37.99 s** over three historical seeds. Preserved artifacts remain unchanged. The table below uses ten **new paired seeds**, Linux SUMO 1.27.1, and policy-independent resolved routes; these scores do not replace historical measurements.

## Final held-out Cologne1 evaluation

| Controller | Mean delay +/- SD (s) | Mean 95% CI (s) | Median (s) | Mean queue | Max queue | Vehicles/h | Completed / 889 | Stops/vehicle | Travel (s) | Switches | Clearance (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Fixed | 59.88 +/- 0.94 | 59.20/60.55 | 56.776 | 19.908 | 57.500 | 1713.400 | 856.700 | 1.090 | 82.704 | 80.000 | 400.000 |
| Max-pressure | 37.75 +/- 2.90 | 35.68/39.82 | 28.510 | 11.212 | 46.500 | 1736.400 | 868.200 | 1.171 | 59.870 | 87.200 | 436.000 |
| ATLAS Original | 66.67 +/- 1.27 | 65.77/67.58 | 61.343 | 23.512 | 63.000 | 1710.000 | 855.000 | 1.089 | 89.297 | 74.000 | 370.000 |
| ATLAS Improved | 20.53 +/- 0.85 | 19.92/21.13 | 11.796 | 4.540 | 22.300 | 1745.200 | 872.600 | 0.686 | 42.402 | 63.700 | 318.300 |

The median column is the mean of per-run vehicle medians. SD and mean confidence intervals describe variation across seeds. Completed-only travel time is separate from the all-scheduled delay objective.

| Paired comparison | Delay reduction (s) | Bootstrap 95% CI (s) | Mean paired reduction | Bootstrap 95% CI (%) | Wins |
|---|---|---|---|---|---|
| vs Fixed | 39.350 | 38.535 / 40.117 | 65.70% | 64.73 / 66.58 | 10/10 |
| vs Max-pressure | 17.220 | 15.511 / 19.156 | 45.32% | 42.69 / 48.27 | 10/10 |
| vs ATLAS Original | 46.142 | 45.403 / 46.814 | 69.21% | 68.50 / 69.88 | 10/10 |

Percentages are the mean of paired per-seed reductions, not a ratio of rounded aggregate means. The primary comparison with original ATLAS is its fresh **66.67 s** score on these same seeds. Comparing 20.53 s with the historical 66.45 s gives a descriptive 69.10% reduction, but is not a paired estimate. Exploratory paired t-tests and effect sizes are included in the raw artifact. These intervals describe this network/demand window, not real-world field-effect uncertainty.

## Per-seed mean delay (s)

| Seed | Fixed | Max-pressure | Original | Improved |
|---|---|---|---|---|
| 5001 | 60.941 | 36.188 | 64.920 | 21.178 |
| 5002 | 59.349 | 33.842 | 67.103 | 19.589 |
| 5003 | 58.934 | 41.595 | 67.351 | 20.254 |
| 5004 | 58.606 | 34.857 | 66.189 | 21.043 |
| 5005 | 59.645 | 35.033 | 65.049 | 19.634 |
| 5006 | 60.782 | 37.945 | 67.399 | 20.427 |
| 5007 | 61.396 | 42.182 | 67.111 | 19.920 |
| 5008 | 58.981 | 38.079 | 67.824 | 21.944 |
| 5009 | 59.949 | 40.463 | 65.194 | 19.766 |
| 5010 | 60.211 | 37.312 | 68.575 | 21.539 |

## Ablations: five separate unseen seeds, no reselection

| Frozen variant | Mean delay (s) | SD (s) |
|---|---|---|
| forecast_on | 19.677 | 0.996 |
| full | 20.143 | 1.071 |
| no_downstream | 20.325 | 1.254 |
| no_forecast | 20.193 | 0.948 |
| no_starvation | 20.019 | 1.070 |
| no_switch_penalty | 20.551 | 0.888 |
| pressure_only | 23.197 | 0.779 |
| queue_only | 26.215 | 1.577 |

The strongest contrast is full MPC **20.143 s** versus queue-only **26.215 s** (23.2% lower aggregate delay); pressure-only is **23.197 s** (full is 13.2% lower). Removing switch cost increases mean delay to **20.551 s**. Individual terms have small, noisy effects: no downstream **20.325 s**, no starvation **20.019 s**, and no forecast **20.193 s**. Forecasting helps only **0.049 s / 0.25%** on the ablation mean; this is not compelling evidence of an independent forecasting benefit. The 0.5 forecast-weight diagnostic performs better at **19.677 s**, but does not replace the frozen validation winner. No post-test retuning occurs.

Mean paired delay reduction of full versus each variant (variant delay minus full delay):

| Variant | Full delay reduction (s) | Paired 95% CI (s) |
|---|---|---|
| no_forecast | 0.049 | -0.953 / 0.865 |
| forecast_on | -0.466 | -1.362 / 0.429 |
| no_downstream | 0.182 | -1.454 / 1.524 |
| no_starvation | -0.124 | -0.484 / 0.116 |
| no_switch_penalty | 0.408 | -0.902 / 1.718 |
| pressure_only | 3.054 | 1.649 / 4.394 |
| queue_only | 6.072 | 4.885 / 7.182 |

Only the pressure-only and queue-only contrasts have intervals entirely above zero. Individual feature removals have intervals including zero; they do not establish separate causal benefit.

## Stress and untuned transfer

| Cologne demand variant | Fixed (s) | Max-pressure (s) | Improved (s) |
|---|---|---|---|
| nominal | 61.806 | 35.516 | 21.363 |
| low | 46.600 | 27.190 | 14.708 |
| peak | 91.190 | 67.838 | 31.081 |
| imbalance | 90.505 | 49.273 | 26.128 |
| burst | 64.981 | 38.661 | 23.024 |

Each stress variant has only one new seed: these are sensitivity checks, not statistically established improvements per regime. All five beat both comparators.

| Untuned Ingolstadt1, five seeds | Delay +/- SD (s) |
|---|---|
| ATLAS Improved | 40.083 +/- 5.343 |
| Fixed | 37.945 +/- 1.360 |
| Max-pressure | 28.164 +/- 1.851 |

**Transfer failed:** unchanged MPC has 40.083 s delay versus fixed 37.945 s and max-pressure 28.164 s. Paired differences are -5.75% versus fixed (bootstrap interval includes zero) and -43.13% versus max-pressure (interval entirely negative). Smaller stopped queues do not guarantee lower all-vehicle delay: moving-vehicle delays and approach service remain relevant. No Ingolstadt-specific parameter tuning or favorable seed selection was performed. The model uses a simplified lane-level service approximation rather than calibrated movement saturation/turn proportions; network-specific service error is a plausible limitation, not a proven causal diagnosis.

## Selection, performance and limitations

Validation selected `mpc_06` at 32.759 s equally weighted mean across five demand variants. Best pressure finalist: `pressure_03`, 35.369 s. All twenty candidate configurations and all 133 tuning/validation runs remain in `signal_control_selection.json`. Final reporting includes 40 paired final runs, 40 ablation runs, 20 stress runs and 15 transfer runs. Mean per-run p95 MPC decision cost on final Cologne seeds is **1.018 ms** on the Docker/Linux developer workstation; this is controller computation, not the separate 29.4 FPS Windows CV pipeline benchmark.

Source legal greens, action masks, a common 10-60 s green envelope, 3 s yellow and 2 s all-red constrain every action. The 180 s lane starvation priority is a heuristic and does not certify a universal vehicle wait bound. Arrival EWMA counts observed lane entries, including lane changes; turning observations are diagnostic, not a trained turn forecast. No pedestrian demand exists here. No field intervention, general network superiority, calibrated spillback capacity, or real safety benefit is established. Native Windows same-seed drift is disclosed in the [audit](signal-control-audit.md); the final evaluator is Linux.

## Reproduce

Prepare only the pinned research sources (raw files remain ignored), then use the dedicated CPU evaluator:

```powershell
docker build -f docker/signal-evaluation.Dockerfile -t atlas-signal-study .
docker run --rm --mount "type=bind,source=$PWD,target=/study" --entrypoint python atlas-signal-study scripts/prepare_real_data.py --only resco --resco-scenario cologne1
docker run --rm --mount "type=bind,source=$PWD,target=/study" --entrypoint python atlas-signal-study scripts/prepare_real_data.py --only resco --resco-scenario ingolstadt1
docker run --rm --mount "type=bind,source=$PWD,target=/study" atlas-signal-study --stage all
# Fresh execution of the selected policy; no tuning:
docker run --rm --mount "type=bind,source=$PWD,target=/study" --entrypoint python atlas-signal-study scripts/run_signal_controller.py --seed 5001 --fresh
python scripts/export_artifacts.py
```

Stages may be run individually as `audit`, `train`, `validate`, `final`, `ablations`, `generalize`, and `publish`, in that order. Training never reads final/ablation/transfer results. Cache acceptance requires matching source/configuration/platform checksums; `selected_profile()` rejects a runtime source different from the frozen profile. The public [optimization replay](https://atlas-mu-murex.vercel.app/optimization) uses actual sampled final-seed output, not live Vercel SUMO execution.
