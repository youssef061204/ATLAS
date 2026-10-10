"""Small product responses derived from actual, separately versioned evidence."""

import json

from atlas import config
from atlas.city_network import sha

CITIES = ("toronto", "london", "seattle", "austin", "calgary")


def read(relative):
    path = config.ARTIFACTS / relative
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def benchmark_summary():
    source = {
        "detection": "benchmarks/real_detection.json",
        "tracking": "benchmarks/real_tracking.json",
        "pipeline": "benchmarks/real_video_pipeline.json",
        "graph": "cities/graph-forecast.json",
    }
    values = {k: read(v) for k, v in source.items()}
    graph = next(r for r in values["graph"]["results"] if r["horizon_minutes"] == 5)
    graph_model = next(r for r in graph["models"] if r["model"] == graph["selected_on_validation"])
    return {
        "map50": values["detection"]["metrics"]["map50"],
        "idf1": values["tracking"]["metrics"]["IDF1"],
        "pipeline_fps": values["pipeline"]["metrics"]["pipeline_fps"],
        "graph_mae_5_mph": graph_model["metrics"]["mae"],
        "provenance": {
            "vision": "Historical UA-DETRAC, three complete annotated sequences",
            "graph": "Historical METR-LA highway observations; not a city intersection forecast",
            "mode": "recorded_verified_benchmarks",
            "sources": {
                k: {"artifact": v, "sha256": sha(config.ARTIFACTS / v)} for k, v in source.items()
            },
        },
    }


def city_summary(city):
    if city not in CITIES:
        raise ValueError("Unknown supported city")
    index = read("cities/v4/data-index.json")
    forecast = read("cities/v4/city-forecast.json")
    historical = (
        next((r for r in index.get("cities", []) if r["city"] == city), None) if index else None
    )
    prediction = (
        next((r for r in forecast.get("cities", []) if r["city"] == city), None)
        if forecast
        else None
    )
    transfer = (
        next(
            (r for r in forecast.get("leave_one_city_out", []) if r["held_out_city"] == city), None
        )
        if forecast
        else None
    )
    return {
        "city": city,
        "version": "atlas-4",
        "historical_data": [historical] if historical else [],
        "forecast": prediction,
        "transfer": transfer,
        "control": [
            row
            for row in (read("cities/v4/controller-heldout-nominal.json") or {}).get(
                "summaries", []
            )
            if row["city"] == city
        ],
        "validation": {
            "field_calibrated": False,
            "limitations": [
                "Official historical counts are separate from current camera snapshots",
                "Forecast target is the next native count interval, not surveyed physical queues",
                "Graph edges use geographic proximity with actual concurrent bins; not surveyed directed flow",
                "SUMO OD and signal plans remain exploratory unless a separate calibration artifact establishes otherwise",
                *(
                    historical.get("limitations", [])
                    if historical
                    else ["Historical source evidence unavailable"]
                ),
            ],
        },
    }


def control_replay():
    source = read("cities/v4/controller-heldout-nominal.json")
    if not source:
        return None
    first_seed = min(row["seed"] for row in source["runs"])
    return {
        **{key: value for key, value in source.items() if key != "runs"},
        "runs": [row for row in source["runs"] if row["seed"] == first_seed],
        "summaries": [
            {
                **row,
                "policy": "network_mpc"
                if row["candidate"] == "cached_original"
                else row["candidate"],
                "mean_delay_s": row["metrics"]["mean_delay_s"],
                "decision_ms_p95": row["metrics"]["decision_ms_p95"],
                "sd": None,
                "ci95": None,
            }
            for row in source["summaries"]
        ],
        "replay_seed": first_seed,
        "evidence": "https://github.com/youssef061204/ATLAS/tree/main/artifacts/cities/v4",
        "scope": "First registered held-out seed replay; summaries retain all 20 paired seeds per city. Generated demand, exploratory signal plans, not field-calibrated traffic effects.",
    }


def control_assessment():
    import numpy as np

    replay = control_replay()
    source = read("cities/v4/controller-heldout-nominal.json")
    if not source or not replay:
        return None
    rows = source["runs"]
    paired = []
    for city in CITIES:
        candidate = {
            r["seed"]: r for r in rows if r["city"] == city and r["policy"] == "network_mpc"
        }
        for baseline in ("fixed", "max_pressure", "original_mpc"):
            reference = [r for r in rows if r["city"] == city and r["policy"] == baseline]
            differences = np.array(
                [
                    r["metrics"]["mean_delay_s"] - candidate[r["seed"]]["metrics"]["mean_delay_s"]
                    for r in reference
                ]
            )
            percentages = np.array(
                [
                    100 * difference / r["metrics"]["mean_delay_s"]
                    for r, difference in zip(reference, differences, strict=True)
                ]
            )
            indices = np.random.default_rng(44).integers(0, len(reference), (20000, len(reference)))
            paired.append(
                {
                    "city": city,
                    "baseline": baseline,
                    "pairs": len(reference),
                    "paired_difference_ci95": list(
                        map(float, np.percentile(differences[indices].mean(axis=1), [2.5, 97.5]))
                    ),
                    "paired_percent_ci95": list(
                        map(float, np.percentile(percentages[indices].mean(axis=1), [2.5, 97.5]))
                    ),
                }
            )
    return {
        **replay,
        "runs": [
            {
                **{
                    key: r[key]
                    for key in (
                        "city",
                        "policy",
                        "seed",
                        "duration",
                        "scenario",
                        "network_sha256",
                        "routes_sha256",
                        "initial_states",
                    )
                },
                "metrics": {
                    key: r["metrics"][key]
                    for key in ("mean_delay_s", "decision_ms_p95", "modeled_safety_violations")
                },
                "trace": [],
                "decisions": [],
            }
            for r in rows
        ],
        "paired": paired,
        "scope": "Complete 20-seed nominal cohort for advisory assessment. Mean simulated delay projections depend on user assumptions; not field-calibrated municipal ROI.",
        "source_sha256": sha(config.ARTIFACTS / "cities/v4/controller-heldout-nominal.json"),
    }
