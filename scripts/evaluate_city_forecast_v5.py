"""Scale-invariant forecast regression and strict source-only LOCO evaluation."""

import gzip
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from atlas.city_data_v4 import stamp
from atlas.city_forecast_v4 import samples
from atlas.city_forecast_v5 import (
    SourceInvariantForecaster,
    causal_scale,
    interval_metrics,
    interval_radius,
    persistence,
)
from threadpoolctl import threadpool_limits


def metrics(rows, predictions):
    error = np.asarray([r["actual"] for r in rows]) - predictions
    return {
        "examples": len(rows),
        "mae_count": float(np.abs(error).mean()),
        "rmse_count": float(np.sqrt(np.mean(error**2))),
        "interval_seconds": sorted({r["interval_seconds"] for r in rows}),
    }


def normalized_errors(rows, predictions):
    scale = causal_scale(rows) * np.asarray([r["interval_seconds"] / 3600 for r in rows])
    return np.abs(np.asarray([r["actual"] for r in rows]) - predictions) / scale


def balanced_score(rows, predictions):
    values = normalized_errors(rows, predictions)
    cities = sorted({r["city"] for r in rows})
    return float(
        np.mean(
            [
                np.mean([v for r, v in zip(rows, values, strict=True) if r["city"] == city])
                for city in cities
            ]
        )
    )


def improvement_gate(rows, candidate, protocol):
    delta = normalized_errors(rows, persistence(rows)) - normalized_errors(rows, candidate)
    groups = defaultdict(lambda: defaultdict(list))
    for row, value in zip(rows, delta, strict=True):
        groups[row["city"]][row["date"]].append(value)
    total_dates = len({r["date"] for r in rows})
    if total_dates < protocol["minimum_validation_dates_for_promotion"]:
        return {
            "accepted": False,
            "reason": "insufficient validation dates",
            "dates": total_dates,
            "interval": None,
        }
    rng = np.random.default_rng(protocol["bootstrap_seed"])
    estimates = np.zeros(protocol["bootstrap_replicates"])
    for city_dates in groups.values():
        means = np.asarray([np.mean(v) for v in city_dates.values()])
        draws = rng.integers(0, len(means), (len(estimates), len(means)))
        estimates += means[draws].mean(axis=1) / len(groups)
    interval = np.quantile(estimates, [0.025, 0.975]).tolist()
    return {
        "accepted": interval[0] > 0,
        "interval": interval,
        "dates": total_dates,
        "scope": "equal-city whole-date bootstrap normalized error reduction on validation only",
    }


def select(train, validation, protocol):
    results, models = [], {}
    for candidate in protocol["candidates"]:
        started = time.perf_counter()
        model = SourceInvariantForecaster(train, candidate)
        prediction, drift = model.predict(validation)
        models[candidate] = model
        results.append(
            {
                "candidate": candidate,
                "validation_normalized_mae_balanced_by_city": balanced_score(
                    validation, prediction
                ),
                "validation": metrics(validation, prediction),
                "validation_drift_fraction": float(drift.mean()),
                "fit_and_validation_wall_s": time.perf_counter() - started,
                "gate": improvement_gate(validation, prediction, protocol),
            }
        )
    best = min(results, key=lambda r: r["validation_normalized_mae_balanced_by_city"])
    selected = best["candidate"] if best["gate"]["accepted"] else "persistence"
    return models[selected], results, models


def report(model, val, test):
    vp, _ = model.predict(val)
    started = time.perf_counter()
    prediction, drift = model.predict(test)
    elapsed = time.perf_counter() - started
    base = metrics(test, persistence(test))
    result = metrics(test, prediction)
    radius = interval_radius(val, vp)
    return {
        "selected_candidate": model.candidate,
        "final": result,
        "persistence": base,
        "mae_reduction_vs_persistence_pct": 100
        * (base["mae_count"] - result["mae_count"])
        / base["mae_count"]
        if base["mae_count"] > 0
        else None,
        "drift_fallback_fraction": float(drift.mean()),
        "inference_wall_ms_total": 1000 * elapsed,
        "interval": interval_metrics(test, prediction, radius),
        "interval_normalized_radius": radius,
    }


def main():
    path = Path("docs/city-forecast-v5-protocol.json")
    protocol = json.loads(path.read_text())
    partitions, metadata = {}, {}
    for city in protocol["cities"]:
        source = Path(f"artifacts/cities/v4/data-{city}.json.gz")
        rows, info = samples(json.loads(gzip.decompress(source.read_bytes())))
        partitions[city] = {
            name: [r for r in rows if r["split"] == name]
            for name in ("train", "validation", "test")
        }
        metadata[city] = {
            "data_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "split": info,
            "final_is_new_unseen_cohort": False,
        }
    local, transfer = [], []
    with threadpool_limits(limits=4):
        for city in protocol["cities"]:
            parts = partitions[city]
            model, candidates, models = select(parts["train"], parts["validation"], protocol)
            row = {
                "city": city,
                **metadata[city],
                **report(model, parts["validation"], parts["test"]),
                "candidates": candidates,
                "candidate_final_regression_metrics": {
                    name: metrics(parts["test"], m.predict(parts["test"])[0])
                    for name, m in models.items()
                },
            }
            # Identical ratio features with the geographic modality: independent ablation.
            graph_model = SourceInvariantForecaster(parts["train"], "ridge_1", geographic=True)
            plain_model = models["ridge_1"]
            row["geographic_ablation"] = {
                "scope": "proximity only; no directed road-network validation",
                "geographic_final": metrics(parts["test"], graph_model.predict(parts["test"])[0]),
                "temporal_only_final": metrics(
                    parts["test"], plain_model.predict(parts["test"])[0]
                ),
                "neighbor_coverage_fraction": metadata[city]["split"]["neighbor_coverage_fraction"],
            }
            local.append(row)
            source_cities = [c for c in protocol["cities"] if c != city]
            train = [r for c in source_cities for r in partitions[c]["train"]]
            val = [r for c in source_cities for r in partitions[c]["validation"]]
            model, candidates, models = select(train, val, protocol)
            transfer.append(
                {
                    "held_out_city": city,
                    "source_cities": source_cities,
                    "target_label_rows_used": 0,
                    "target_normalization_statistics_used": False,
                    **report(model, val, parts["test"]),
                    "candidates": candidates,
                    "candidate_final_regression_metrics": {
                        name: metrics(parts["test"], m.predict(parts["test"])[0])
                        for name, m in models.items()
                    },
                    "final_is_new_unseen_cohort": False,
                }
            )
            print(
                city,
                "local",
                local[-1]["selected_candidate"],
                round(local[-1]["final"]["mae_count"], 3),
                "LOCO",
                transfer[-1]["selected_candidate"],
                round(transfer[-1]["final"]["mae_count"], 3),
                flush=True,
            )
    artifact = {
        "schema_version": "atlas-city-forecast-results-5.0",
        "generated_at": stamp(),
        "protocol_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(
            Path("backend/atlas/city_forecast_v5.py").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "local": local,
        "zero_shot": transfer,
        "production_promoted": False,
        "limitations": [
            protocol["scope"],
            "Existing final partitions have been reported previously; new independent cohorts are needed for a promotion decision.",
            "Chronological validation intervals are not guaranteed under distribution shift.",
            "No weather, incident, current camera, verified directed graph or supervised queue modality is invented.",
        ],
    }
    output = Path("artifacts/cities/v5/forecast-results.json")
    output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
