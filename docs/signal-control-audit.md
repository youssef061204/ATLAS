# Signal controller audit and replacement

The original result remains byte-for-byte in `artifacts/benchmarks/realistic_signal_control.json` and `original_signal_control_failed.json`: original ATLAS **66.45 s**, fixed **57.45 s**, max-pressure **37.99 s**, over historical seeds 42–44. The replacement is evaluated separately; historical scores are never overwritten or substituted into new paired statistics.

## Original architecture

`evaluation/signal.py` selected an offline cyclic timing plan from six candidates using seeds 1001/2002 during 07:00–07:30. Only phases 2/6 varied; six auxiliary phases were always 12 s. The selected cycle `[12,12,40,12,12,12,40,12]` was 192 s including eight 5 s clearances, versus 180 s for the published fixed cycle. It then ran unchanged during 07:30–08:00 on seeds 42–44. Despite the ATLAS name, its runtime decision was independent of queues, downstream density, arrivals, waiting, and turning demand. Its selection objective was mean all-scheduled delay + 0.15 maximum queue + 0.1 worst observed approach delay. Fixed auxiliary timings of 10 s were absent from the candidate set.

The original max-pressure comparator uses current upstream-minus-downstream density over controlled movements, 12 s minimum hold, 60 s maximum hold, a one-unit switching threshold, and a 180 s phase-service starvation bound. This action logic is preserved unchanged. The portable two-phase simulator in `simulation.py`, the independent `benchmark_sumo.py`, and the historical experiment hooks were also reviewed. Those controlled experiments remain explicitly separate from the eight-phase RESCO evaluation.

## Paired harness

The new evaluator uses the same pinned RESCO Cologne1 source, SUMO 1.27.1, 1 s steps, 1,800 s horizon, no warm-up, teleport disabled, and initial source phase 0. It resolves OD trips with seeded `duarouter` before the episode: every paired controller must have identical scheduled-demand **and resolved-route SHA-256**, legal phases, controlled movement mapping, network, seed, and demand window. It uses only source legal green states, including SUMO's yielding permissive movements; it does not invent green combinations. All policies share a 10–60 s actuator envelope, 3 s yellow, and 2 s all-red. Policy hold thresholds may be more conservative (historical max-pressure remains 12 s); this does not relax safety for the replacement or weaken the comparator.

Delay is the same `trip_metrics` implementation for all controllers: `timeLoss + departDelay` across **all scheduled vehicles**, including unfinished trips. Uninserted vehicles incur horizon-minus-scheduled-departure waiting. Completed-only travel time is reported separately. No pedestrian demand exists in these scenarios; pedestrian validation is not claimed.

Every observation is from the current 1 Hz TraCI subscriptions; the evaluator asserts the simulator timestamp before taking each action. Every commanded state is a source green or an explicit yellow/all-red clearance. There is no additional one-step action lag, repeated clearance, custom conflict combination, or controller-specific delay accounting. Reset constructs fresh controller, actuator, subscriptions, and SUMO process. Movement accumulation is sorted to remove Python hash-order floating arithmetic variation.

Native Windows SUMO repeated runs exhibited a small same-seed drift even for identical cyclic signal commands: fixed 56.901/56.973 s and original ATLAS 66.728/67.267 s. This also reproduced in the untouched original harness, so it is not attributed to the new feedback logic. The underlying simulator cause was not established. Final experiments run in the Linux evaluator, which passed fresh repeated-run checks (three identical original seed-42 runs at 67.267 s), and platform is part of the cache signature. We do not claim Windows/Linux numerical equivalence. The historical artifact keeps its original Windows results.

## Tested failure hypotheses

The historical audit seed 42 produces original ATLAS 67.267 s versus max-pressure 39.216 s in the paired Linux harness. Eight standalone diagnostic plots per audit compare queues, cumulative observed delay, phase occupancy, switch count, completed departures, starvation, phase pressure, and cumulative queue/transition cost. Full per-second diagnostic JSONL files remain local because they are scratch traces; published results record their checksums and the replay retains actual samples.

| Hypothesis | Evidence and finding |
|---|---|
| Excessive switching | Rejected as the main cause: original 74 switches / 370 s clearance, max-pressure 89 / 445 s. Original still loses despite **less** clearance time. |
| Insufficient demand-responsive switching | Supported: original cycles through all phases independent of demand. Its observed mean queue is 23.698 vehicles versus 11.657 for max-pressure; worst approach delay is 99.447 s versus 58.646 s. |
| Reward / selection weakness | Supported: six timing candidates exclude the unchanged fixed schedule. Setting the original cyclic policy to the exact fixed timings reproduces fixed 56.901 s, improving 10.366 s without changing the actuator or metric. This isolates a timing-selection defect, rather than a special ATLAS transition penalty. |
| Missing state | Confirmed by code and action logs: original phase choice ignores fresh queues, movement pressures, downstream congestion, causal arrivals, waiting, and turn observations. Max-pressure uses the same observations dynamically. |
| Wrong normalization | Lane capacities use length/7.5 and pressure is density, not raw queue count. Hand-calculated unit tests pass. Original timing selection does not consume pressure, so pressure normalization cannot explain its cyclic actions. New score weights are selected on validation, not on test seeds. |
| Action / movement mismatch | Controlled links map source signal indices to actual upstream/downstream lanes. Mapping and deduplication tests pass; paired policies share that mapping and legal state strings. No mismatch was detected. |
| Stale observations / lag | Current simulator timestamp is asserted every step; requested and executed states are logged before advancing. Safety masking and clearance account for intentional deferred greens. No stale observation defect was detected. |
| Weak optimizer | Confirmed structurally and by the fixed-equivalent intervention: a small offline timing grid cannot respond to the demand shift. Replacement families include feedback pressure and causal queue prediction. |
| Demand overfit | Original tuning and final demand periods differ and its timings remain fixed. The historical result shows failed transfer, but does not isolate demand shift from the restricted grid. New selection spans five demand variants with separate tuning/validation/test seeds. |
| SUMO integration | Shared actuator tests verify min/max hold, invalid actions, exact yellow/all-red, no oscillation, and reset. Fixed-equivalent replay matches fixed. Windows drift is separately disclosed and excluded from final evaluation. |

On audit seed 42, the original has 242 green seconds with **no vehicles on its served lanes while other lanes queue**, versus 157 for max-pressure. This diagnostic excludes moving vehicles, so it is not simply counting green time without stopped vehicles.

## Replacement candidates

Twelve pressure candidates combine upstream/downstream normalized movement density with validation-selected queue, waiting, starvation, arrival-EWMA, and switching terms. Eight predictive candidates use a short-horizon fluid queue model. The planner considers legal phase sequences, charges each switch five seconds of lost service, limits service under downstream density, includes queue area, maximum queue, starvation and spillback penalties, executes only the first action, and replans. It never sees future trips or clones the future SUMO simulation. Observed turning counts are logged for diagnosis; source movement topology determines service masks. No calibrated turn-proportion forecast is claimed.

Causal lane arrivals use a 1 Hz EWMA. METR-LA highway speed prediction is a different target and is not relabeled as junction arrival accuracy. MPC supplies the justified predictive family; a learned/deep RL policy was unnecessary to test this engineering hypothesis.

The selected profile is `mpc_06`: horizon 30 s, beam width 6, service rate 0.65 vehicles/s, minimum green 12 s, maximum 60 s, 1 s decisions, switching cost 0.5, maximum-queue weight 0.15, starvation weight 0.25, downstream weight 1, forecast weight 1, and 180 s demand-bearing starvation priority. Those values come from the declared validation comparison, not final seeds.

## Predeclared selection and evidence

`signal-control-protocol.json` declares all twenty configurations and disjoint sets: ten tuning cases (1001–1010), five validation cases (3001–3005), ten final seeds (5001–5010), five separate ablation seeds (6001–6005), five untuned Ingolstadt1 seeds (7001–7005), and five final stress cases (8001–8005). Demand variants are nominal, 70% subsampled volume, 30% extra trips, directional imbalance, and compressed burst departures. These are deterministic perturbations of published OD demand, not additional real field observations.

Successive halving runs all twenty configurations on two nominal tuning seeds, promotes three per family, then evaluates those six across the remaining eight tuning cases. The six finalists are evaluated on five separate validation demand cases. Minimum equally weighted validation mean all-scheduled delay selects the winner. The frozen profile and SHA-256 of the protocol, controller, and harness are recorded **before** final execution; final stages reject changed source/configuration. No final seed is used for selection.

Results include all candidate runs and failed families, paired per-seed comparisons, mean/median/sample SD, t-based mean confidence intervals, 20,000 fixed-seed bootstrap resamples of paired delay differences, paired percentage improvements, exploratory paired t-tests and Cohen dz. Bootstrap intervals describe seed variability within this network/window, not field-effect uncertainty. The ten-seed nominal final result is not replaced by a favorable stress case.

Separate ablations remove forecasting, downstream terms (including capacity gating), starvation, and switching penalties; pressure-only, queue-only, and an additional forecast-weight-0.5 variant provide comparisons without retuning. Ingolstadt1 uses identical frozen parameters and the source fixed green cycle clamped to the shared 10–60 s envelope (38/10/37 s). Its original 6 s phase is outside that declared envelope, so transfer is an ATLAS paired experiment, not a RESCO leaderboard score.

See [final results](signal-control-results.md) for aggregate outcomes, ablations, transfer limitations, and reproduction commands. Raw evidence is in `artifacts/benchmarks/` under `signal_controller_audit`, `signal_control_selection`, `improved_signal_control`, `signal_control_ablations`, and `signal_control_generalization`.

References: [SUMO signal states and programs](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html), [TraCI signal commands](https://sumo.dlr.de/docs/TraCI/Change_Traffic_Lights_State.html), and [SUMO reproducibility documentation](https://sumo.dlr.de/docs/Simulation/Randomness.html). The new controller is an ATLAS implementation, not an exact reproduction of a published MPC algorithm.
