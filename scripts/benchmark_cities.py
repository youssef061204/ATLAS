"""Paired exploratory five-city experiment; smoke runs are not city validation."""

import argparse
import json
from pathlib import Path

import numpy as np
from atlas.cities import city_configs, now
from atlas.evaluation.network_v2 import run_network
from scipy import stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--city", choices=[*city_configs(), "all"], default="all")
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--seed-start", type=int, default=15001)
    p.add_argument("--duration", type=int, default=300)
    p.add_argument(
        "--policies",
        nargs="+",
        choices=["fixed", "max_pressure", "original_mpc", "risk_mpc"],
        default=["fixed", "max_pressure", "original_mpc", "risk_mpc"],
    )
    p.add_argument(
        "--scenario", choices=["nominal", "sensor_outage", "lane_closure"], default="nominal"
    )
    p.add_argument("--output", type=Path, default=Path("artifacts/cities/experiments.json"))
    args = p.parse_args()
    path = args.output
    payload = {
        "schema_version": "atlas-city-experiments-2.0",
        "recorded_at": now(),
        "scope": "Exploratory uncalibrated OSM network smoke experiments; assumed demand, not field impact",
        "split": "Predeclared smoke seeds; no policy tuning or publication heldout claim",
        "runs": [],
        "summaries": [],
        "failures": [],
    }
    for city in city_configs() if args.city == "all" else [args.city]:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            paired = []
            for policy in args.policies:
                try:
                    r = run_network(city, policy, seed, args.duration, scenario=args.scenario)
                    paired.append(r)
                    payload["runs"].append(r)
                except Exception as exc:
                    payload["failures"].append(
                        {"city": city, "seed": seed, "policy": policy, "reason": str(exc)}
                    )
                    print(city, policy, "FAILED", exc, flush=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
            if paired and any(
                (r["network_sha256"], r["routes_sha256"], r["initial_states"])
                != (
                    paired[0]["network_sha256"],
                    paired[0]["routes_sha256"],
                    paired[0]["initial_states"],
                )
                for r in paired
            ):
                raise ValueError("Unpaired network, routes or initial state")
        for policy in args.policies:
            rows = [r for r in payload["runs"] if r["city"] == city and r["policy"] == policy]
            y = np.array([r["metrics"]["mean_delay_s"] for r in rows])
            if len(y):
                sd = float(y.std(ddof=1)) if len(y) > 1 else None
                ci = (
                    list(
                        map(
                            float,
                            stats.t.interval(0.95, len(y) - 1, loc=y.mean(), scale=stats.sem(y)),
                        )
                    )
                    if len(y) > 1 and sd
                    else None
                )
                payload["summaries"].append(
                    {
                        "city": city,
                        "policy": policy,
                        "seeds": len(y),
                        "mean_delay_s": float(y.mean()),
                        "sd": sd,
                        "ci95": ci,
                        "decision_ms_p95": float(
                            np.mean([r["metrics"]["decision_ms_p95"] for r in rows])
                        ),
                    }
                )
    path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
