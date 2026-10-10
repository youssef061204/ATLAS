# ATLAS 4 control research

Historical controllers and benchmark evidence remain unchanged. This work uses new `control_v4.py` and `evaluation/network_v4.py`; neither controls municipal hardware nor automatically replaces production models.

## Regression diagnosis

The frozen v2 city networks contain only two or three source green phases per controllable intersection. Every sampled decision outside a mandatory safety hold activates `small_phase_pressure_fallback`. The advertised risk search and coordination objectives therefore do not execute in those corridors. Toronto, Seattle and Calgary are exactly equal to max-pressure over the twenty-seed cohort; London and Austin differ marginally because of decision timing.

Calgary remains a substantive failure: fixed averages 18.621 seconds, prototype/max-pressure 21.264 seconds, original MPC 19.131 seconds. The original often switches more while producing less delay. Optimizing switch count or assuming a small topology implies reliable pressure control is inadequate. See [actual archived trace diagnosis](../artifacts/cities/v4/controller-diagnosis.json). Generated OD and unsurveyed signal timing limit external validity.

## Separate candidate

The new candidate caches movement masks and destination topology, batches all feasible beam expansions, retains causal lane-arrival EWMA, and independently passes actions to the existing modeled safety gate. Topology never silently replaces its optimization with pressure. Configurable queue-tail, fairness, downstream density, clearance cost, horizon, service rate and graph hints are experimental objectives. Bus/pedestrian outcomes and physical spillback are explicitly unavailable when inputs do not support them.

The neutral configuration reproduces the frozen original's actions on 1,000 matched eight-phase snapshots. Interleaved host p95 is 0.585 versus 2.084 ms; this is decision timing on synthetic snapshots, excludes SUMO/HTTP and does not establish a production SLA. Both policies share a process, so its RSS is not a policy-specific memory comparison. See [profile](../artifacts/cities/v4/controller-profile.json).

The v4 harness batches real TraCI vehicle subscriptions and uses the network's actual coordinate transformation for replay. Five actual paired v3/v4 seed-41003 episodes preserve delay, completion, queues, stops, CO2/fuel and switches exactly, and positions/speeds within 0.00001. Recorded v4 wall times are recorded in the evidence artifact in those single pairs. Shared-host timing is not an isolated repeated speedup. See [equivalence check](../artifacts/cities/v4/subscription-equivalence.json).

## Evaluation discipline

Development seeds are 41001 to 41005, validation 42001 to 42005, and reserved final seeds 43001 to 43020. Candidate selection must finish before final seeds run. All candidate outcomes, regressions, failed runs and rejected development diagnostics are retained. Half/full/double generated OD demand are sensitivity regimes, not independently calibrated municipal traffic. Both members of each pair use identical network/route hashes, duration, scenario, initial lamps and simulator seed.

The harness permits an explicit source-hashed learned controller factory for separate research. Actual SUMO remains the benchmark oracle. Models, graph hints and surrogate predictions cannot bypass clearance, minimum/maximum green or source phase masks. The [frozen configuration](control-v4-frozen.json) selects the neutral cached policy after all objective/rate/horizon alternatives fail city-level development guards. All twenty final seeds per city and demand regime have completed. The 1,800-run final cohort preserves original traffic outcomes; high-demand Seattle regresses against max-pressure. Cooperative Q improves three nominal city rotations but regresses in two and remains experimental. See [complete measured results](atlas-4-results.md), including raw evidence and the retained serialization failure/recovery.
