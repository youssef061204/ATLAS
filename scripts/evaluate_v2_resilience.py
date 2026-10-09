"""Matched sensor outage/lane slowdown runs and a declared ablation smoke study."""

import json
from dataclasses import replace
from pathlib import Path

from atlas.control_v2 import RiskConfig
from atlas.evaluation.network_v3 import run_network


def main():
    runs = []
    for scenario in ("sensor_outage", "lane_closure"):
        for policy in ("fixed", "max_pressure", "original_mpc", "risk_mpc"):
            runs.append(run_network("austin", policy, 22001, scenario=scenario))
    variants = {
        "full": RiskConfig(),
        "no_coordination": replace(RiskConfig(), coordination_weight=0),
        "no_forecast": replace(RiskConfig(), forecast_weight=0),
        "no_risk": replace(RiskConfig(), risk_weight=0),
        "fixed_budget": replace(RiskConfig(), dynamic_budget=False),
        "no_tail": replace(RiskConfig(), tail_weight=0),
        "no_spillback_cost": replace(RiskConfig(), spillback_weight=0),
        "no_topology_fallback": replace(RiskConfig(), small_phase_pressure_fallback=False),
    }
    ablations = []
    for name, settings in variants.items():
        run = run_network(
            "austin", "risk_mpc", 22002, settings=settings, coordinated=name != "no_coordination"
        )
        ablations.append({"variant": name, "run": run})
    Path("data/resilience-v3.json").write_text(
        json.dumps(
            {
                "scope": "Single-seed development sensitivity tests, not statistical incident-detection or ablation validation",
                "outage_visibility": "Uniform sensor removal and common deterministic safety fallback for all adaptive controllers",
                "runs": runs,
                "ablations": ablations,
            },
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
