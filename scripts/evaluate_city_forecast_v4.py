"""Frozen chronological official-count forecasting and four-city zero-shot evaluation."""

import gzip
import json
import time
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from atlas.cities import now
from atlas.city_forecast_v4 import (
    TrainingScale,
    conformal_radius,
    fit_neural,
    neural_predictions,
    paired_date_interval,
    samples,
)
from atlas.city_network import sha
from sklearn.ensemble import HistGradientBoostingRegressor


def metrics(rows, prediction):
    error = np.asarray([r["actual"] for r in rows]) - prediction
    return {
        "examples": len(rows),
        "mae_count_per_native_interval": float(np.abs(error).mean()),
        "rmse_count_per_native_interval": float(np.sqrt((error**2).mean())),
        "mean_actual_count": float(np.mean([r["actual"] for r in rows])),
        "interval_seconds": sorted({r["interval_seconds"] for r in rows}),
    }


def calendar_key(row):
    return (row["site_id"], row["direction"], row["interval_seconds"], row["time"][11:16])


def main():
    protocol_path = Path("docs/city-forecast-v4-protocol.json")
    protocol = json.loads(protocol_path.read_text())
    root = Path("artifacts/cities/v4")
    model_root = Path("data/models/city-v4")
    model_root.mkdir(parents=True, exist_ok=True)
    datasets, results, splits, runtime_cards = {}, [], {}, {}
    for city in protocol["cities"]:
        path = root / f"data-{city}.json.gz"
        if not path.exists():
            raise ValueError(f"Actual official data is required for {city}")
        document = json.loads(gzip.decompress(path.read_bytes()))
        rows, split = samples(document)
        splits[city] = split
        partitions = {
            s: [r for r in rows if r["split"] == s] for s in ("train", "validation", "test")
        }
        dataset_info = {
            "city": city,
            "data_sha256": sha(path),
            "split": split,
            "source_rows": len(document["records"]),
            "sites": len(document["sites"]),
            "partition_examples": {k: len(v) for k, v in partitions.items()},
        }
        minimum = protocol["minimum"]
        if any(len(partitions[name]) < minimum[f"{name}_examples"] for name in partitions):
            results.append(
                {
                    **dataset_info,
                    "status": "insufficient_chronological_examples",
                    "models": [],
                    "limitations": [
                        "No forecast or fabricated score; source does not support the registered split"
                    ],
                }
            )
            continue
        datasets[city] = partitions
        train, val, test = (partitions[k] for k in ("train", "validation", "test"))
        predictions, models = {}, []
        predictions["persistence"] = {
            name: np.asarray(
                [r["history_flow_vph"][-1] * r["interval_seconds"] / 3600 for r in rows]
            )
            for name, rows in (("validation", val), ("test", test))
        }
        calendar = defaultdict(list)
        for row in train:
            calendar[calendar_key(row)].append(row["actual"])
        overall = float(np.median([r["actual"] for r in train]))
        predictions["training_calendar_median"] = {
            name: np.asarray(
                [
                    float(np.median(calendar[calendar_key(r)]))
                    if calendar_key(r) in calendar
                    else overall
                    for r in rows
                ]
            )
            for name, rows in (("validation", val), ("test", test))
        }
        scale = TrainingScale(train)
        started = time.perf_counter()
        settings = protocol["hgb"]
        estimator = HistGradientBoostingRegressor(
            max_iter=settings["max_iter"],
            max_leaf_nodes=settings["max_leaf_nodes"],
            l2_regularization=settings["l2_regularization"],
            random_state=settings["seed"],
            early_stopping=False,
        )
        estimator.fit(scale.features(train), scale.targets(train))
        hgb_seconds = time.perf_counter() - started
        hgb_path = model_root / f"{city}-histogram_gradient_boosting.joblib"
        joblib.dump(estimator, hgb_path)
        checkpoints = {
            "histogram_gradient_boosting": {"path": hgb_path.name, "sha256": sha(hgb_path)}
        }
        scales = {"histogram_gradient_boosting": {"mean": scale.mean, "std": scale.std}}
        predictions["histogram_gradient_boosting"] = {
            name: scale.counts(estimator.predict(scale.features(rows)), rows)
            for name, rows in (("validation", val), ("test", test))
        }
        training_info = {"histogram_gradient_boosting": {"training_seconds": hgb_seconds}}
        for name, graph in (("temporal_mlp", False), ("geographic_message_network", True)):
            started = time.perf_counter()
            model, nscale, info = fit_neural(train, val, graph, protocol["neural"])
            training_info[name] = {**info, "training_seconds": time.perf_counter() - started}
            predictions[name] = {
                partition: neural_predictions(model, nscale, rows)
                for partition, rows in (("validation", val), ("test", test))
            }
            import torch

            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "scale": {"mean": nscale.mean, "std": nscale.std},
                    "graph": graph,
                    "protocol_sha256": sha(protocol_path),
                    "data_sha256": sha(path),
                },
                model_root / f"{city}-{name}.pt",
            )
            checkpoints[name] = {
                "path": f"{city}-{name}.pt",
                "sha256": sha(model_root / f"{city}-{name}.pt"),
            }
            scales[name] = {"mean": nscale.mean, "std": nscale.std}
        for name in protocol["candidates"]:
            prediction = predictions[name]
            models.append(
                {
                    "name": name,
                    "validation": metrics(val, prediction["validation"]),
                    "test": metrics(test, prediction["test"]),
                    **training_info.get(name, {}),
                }
            )
        selected = min(
            models, key=lambda r: (r["validation"]["mae_count_per_native_interval"], r["name"])
        )["name"]
        runtime_cards[city] = {
            "validation_selected": selected,
            "data_sha256": sha(path),
            "protocol_sha256": sha(protocol_path),
            "checkpoints": checkpoints,
            "scales": scales,
            "feature_source_sha256": sha("backend/atlas/city_forecast_v4.py"),
        }
        radius = conformal_radius([r["actual"] for r in val], predictions[selected]["validation"])
        chosen = predictions[selected]["test"]
        actual = np.asarray([r["actual"] for r in test])
        uncertainty = {
            "nominal_coverage": 0.9,
            "calibration_examples": len(val),
            "radius_count": radius,
            "test_coverage": float(np.mean(np.abs(actual - chosen) <= radius))
            if radius is not None
            else None,
            "mean_width_count": float(np.mean(chosen + radius - np.maximum(0, chosen - radius)))
            if radius is not None
            else None,
            "scope": "Split-conformal marginal interval; chronological distribution shift can invalidate exchangeability",
        }
        preview = [
            {
                "site_id": r["site_id"],
                "direction": r["direction"],
                "time": r["time"],
                "interval_seconds": r["interval_seconds"],
                "actual": r["actual"],
                "predicted": float(p),
                "persistence": float(b),
                "lower": max(0, float(p - radius)) if radius is not None else None,
                "upper": float(p + radius) if radius is not None else None,
                "observed_neighbors": r["neighbor_sites"],
            }
            for r, p, b in list(zip(test, chosen, predictions["persistence"]["test"], strict=True))[
                :128
            ]
        ]
        results.append(
            {
                **dataset_info,
                "status": "evaluated",
                "models": models,
                "validation_selected": selected,
                "uncertainty": uncertainty,
                "paired_persistence": paired_date_interval(
                    test, predictions["persistence"]["test"], chosen
                ),
                "preview_selection": "First 128 source-ordered test examples, not favorable cases",
                "preview": preview,
                "field_twin_calibrated": False,
            }
        )
        print(
            city,
            selected,
            metrics(test, chosen),
            "coverage",
            uncertainty["test_coverage"],
            flush=True,
        )
    transfers = []
    for heldout in protocol["cities"]:
        other = [c for c in protocol["cities"] if c != heldout]
        if heldout not in datasets or any(c not in datasets for c in other):
            transfers.append(
                {
                    "held_out_city": heldout,
                    "status": "insufficient_chronological_data",
                    "trained_cities": [c for c in other if c in datasets],
                    "reason": "Strict four-city rotation is not replaced by fewer cities",
                }
            )
            continue
        train = [r for c in other for r in datasets[c]["train"]]
        val = [r for c in other for r in datasets[c]["validation"]]
        test = datasets[heldout]["test"]
        started = time.perf_counter()
        model, scale, info = fit_neural(train, val, True, protocol["neural"])
        train_seconds = time.perf_counter() - started
        timings = []
        for _ in range(30):
            before = time.perf_counter()
            prediction = neural_predictions(model, scale, test)
            timings.append((time.perf_counter() - before) * 1000)
        baseline = np.asarray(
            [r["history_flow_vph"][-1] * r["interval_seconds"] / 3600 for r in test]
        )
        transfers.append(
            {
                "held_out_city": heldout,
                "status": "evaluated_zero_shot",
                "trained_cities": other,
                "training_examples": len(train),
                "validation_examples": len(val),
                "target_city_fit_examples": 0,
                "training_seconds": train_seconds,
                "model": info,
                "test": metrics(test, prediction),
                "persistence": metrics(test, baseline),
                "paired_persistence": paired_date_interval(test, baseline, prediction),
                "batch_inference_ms_p50": float(np.percentile(timings, 50)),
                "batch_inference_ms_p95": float(np.percentile(timings, 95)),
                "inference_scope": "Whole test batch includes NumPy features and CPU forward pass, excludes HTTP and source ingestion",
                "frozen_training_scale": {"mean": scale.mean, "std": scale.std},
                "ood_fraction_history_z_gt_3": float(
                    np.mean(np.max(np.abs(scale.features(test)[:, :3]), axis=1) > 3)
                ),
                "promoted": False,
            }
        )
        print("zero-shot", heldout, transfers[-1]["test"], flush=True)
    runtime_manifest = model_root / "runtime-manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {"experiment_id": protocol["experiment_id"], "cities": runtime_cards},
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    result = {
        "experiment_id": protocol["experiment_id"],
        "recorded_at": now(),
        "protocol_sha256": sha(protocol_path),
        "source_sha256": {
            "model": sha("backend/atlas/city_forecast_v4.py"),
            "evaluation": sha(__file__),
        },
        "cities": results,
        "leave_one_city_out": transfers,
        "limitations": protocol["limitations"],
        "operational_promotion": False,
        "field_calibration": False,
        "runtime_manifest_sha256": sha(runtime_manifest),
    }
    (root / "city-forecast.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
