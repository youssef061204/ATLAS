# Experimental controller and deterministic actuation

The existing production MPC is preserved. The new `RiskController` is **not promoted to default**: its measured performance and transfer evidence determine its status, not its architecture.

For complex multi-phase intersections, it searches fluid queues over 20–40-second adaptive horizons, keeps up to four beam candidates, prunes illegal holds, reuses its previous action as a tie-break, and bounds candidate expansions at 240. Decision intervals vary between 1 and 3 seconds. Objective terms include queue delay, maximum queue, switch loss, starvation-weighted queues, downstream density and one-hop neighbor hints. These are model-based surrogates, not calibrated person delay or neighborhood equity.

Arrival envelopes are 0.7×, 1× and 1.3× causal EWMA. Empirical CVaR at 0.8 over three assumed equally weighted scenarios adds a tail-risk term. These weights are sensitivity assumptions; no calibrated probabilistic demand model is claimed. Saturation service is 0.65 vehicles/s with downstream density gating. Fluid queues omit detailed turning and running-vehicle travel dynamics.

At intersections with at most three legal green phases, the revised prototype uses the unchanged pressure algorithm as an explicit topology fallback. This responds to prior MPC transfer weakness, but it is not a calibrated OOD detector. Matching max-pressure does not establish an improvement over max-pressure. Small-graph fallback can regress versus original MPC in some cities. Regional supervisory learning, RL and demand-aware green waves are not implemented.

`NetworkCoordinator` constructs one-hop messages from actual destination lane owners, arrivals and available capacity. Its benefit requires an independent-versus-coordinated ablation; the initial Austin sensitivity run does **not** establish a benefit. No GNN is used.

`SafetyGate` alone produces lamps. Common experiment bounds are 10–60 s green, 3 s yellow and 2 s all-red. Adaptive policies retain their own minimum 12 s. Optional explicitly mapped pedestrian phases require walk + clearance hold. Explicit protected-movement conflict pairs are checked at construction; source SUMO phases remain authoritative in imported experiments. Invalid requests are rejected and mapped to deterministic safe cyclic fallback. Maximum wait fairness is a heuristic, not a hard per-person guarantee.

The initial optimizer had an invalid maximum-green hold request; the gate rejected it. An independent unit check led to a correction before the final 34001-series study. Interrupted 33001 diagnostics are preserved separately; no controller settings were selected from final performance. Configuration and source hashes are in `atlas-2-protocol.json`.

Decisions log selected action, permitted phases, first-stage alternative costs, assumed uncertainty, planning horizon, expansion count and fallback reasons. Baseline physics, network, routes, seed, warmup and actuation constraints are paired. Proprietary SCOOT/SCATS/Surtrac are not implemented or compared.
