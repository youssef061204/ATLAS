"""Reproduce saved neural metrics, fixed first-sensor preview, paired day-block CIs."""

import json
from pathlib import Path

import joblib
import numpy as np
import tables
import torch
from atlas.city_network import sha
from atlas.evaluation.forecasting import causal_fill, chronological_masks, forecast_scores
from atlas.forecast_v3 import features
from atlas.graph_runtime import load_checkpoint
from threadpoolctl import threadpool_limits


def main():
    target = Path("artifacts/cities/graph-forecast.json")
    record = json.loads(target.read_text())
    original = json.loads(Path("artifacts/benchmarks/real_forecasting.json").read_text())
    path = Path("datasets/metr-la/metr-la.h5")
    if sha(path) != record["dataset_sha256"]:
        raise ValueError("Source checksum mismatch")
    with tables.open_file(path) as source:
        values = source.root.df.block0_values.read()
        times = source.root.df.axis1.read().astype("datetime64[ns]")
    train_end, val_end = int(len(values) * 0.7), int(len(values) * 0.8)
    filled, valid = causal_fill(values, train_end)
    classical = json.loads(Path("artifacts/cities/forecast-v3.json").read_text())
    context_path = Path("data/models/forecast-v3/context.npz")
    if sha(context_path) != classical["runtime_context_sha256"]:
        raise ValueError("Runtime context mismatch")
    with np.load(context_path, allow_pickle=False) as context:
        means = context["means"]
        sensors = context["sensor_ids"].tolist()
    gap = np.r_[0, np.cumsum(np.diff(times) != np.timedelta64(5, "m"))]
    torch.set_num_threads(4)
    comparisons, previews = [], []
    for study in record["results"]:
        minutes = study["horizon_minutes"]
        h = minutes // 5
        origins = np.arange(6, len(values) - h + 1)
        targets = origins + h - 1
        keep = gap[targets] - gap[origins - 6] == 0
        origins, targets = origins[keep], targets[keep]
        test = chronological_masks(origins, h, train_end, val_end, len(values))["test"]
        history = np.stack([filled[origins - i] for i in range(6, 0, -1)], axis=2)[test]
        observed, mask = values[targets[test]], valid[targets[test]]
        features_x = features(history, times[origins[test] - 1], means)
        predictions = {}
        for candidate in study["models"]:
            checkpoint_path = Path(f"data/models/graph-forecast/{candidate['model']}-{minutes}.pt")
            if sha(checkpoint_path) != candidate["checkpoint_sha256"]:
                raise ValueError("Neural checkpoint mismatch")
            model, checkpoint = load_checkpoint(
                str(checkpoint_path), candidate["checkpoint_sha256"]
            )
            x = (torch.tensor(features_x) - checkpoint["mean"]) / checkpoint["scale"]
            with torch.inference_mode():
                prediction = (
                    np.concatenate([model(part).numpy() for part in x.split(128)]) * 10
                    + history[:, :, -1]
                )
            score = forecast_scores(observed, prediction, mask)
            if not np.isclose(score["mae"], candidate["metrics"]["mae"], atol=1e-10, rtol=0):
                raise ValueError("Saved neural score does not reproduce")
            predictions[candidate["model"]] = prediction
        chosen = predictions[study["selected_on_validation"]]
        # Direct graph-vs-MLP comparison uses equal origin samples/configuration.
        baselines = {"matched_temporal_mlp": predictions["temporal_mlp"]}
        if str(minutes) in original["metrics"]["horizons"]:
            clock = (
                (times[origins[test] - 1] - times[origins[test] - 1].astype("datetime64[D]"))
                .astype("timedelta64[m]")
                .astype(float)
            )
            clock = np.broadcast_to(clock[:, None], history.shape[:2])
            frozen = np.stack(
                [
                    history[:, :, -1],
                    history[:, :, -2],
                    history[:, :, -5],
                    history.mean(axis=2),
                    history[:, :, -3:].mean(axis=2),
                    history.std(axis=2),
                    np.sin(2 * np.pi * clock / 1440),
                    np.cos(2 * np.pi * clock / 1440),
                ],
                axis=2,
            ).astype(np.float32)
            oldpath = Path(f"artifacts/models/metr-la-forecast-{minutes}.joblib")
            with threadpool_limits(limits=4):
                old = joblib.load(oldpath).predict(frozen.reshape(-1, 8)).reshape(observed.shape)
            if not np.isclose(
                forecast_scores(observed, old, mask)["mae"],
                original["metrics"]["horizons"][str(minutes)]["atlas_gradient_boosting"]["mae"],
                atol=1e-10,
                rtol=0,
            ):
                raise ValueError("Original score mismatch")
            baselines["original_atlas_ml"] = old
        day = times[targets[test]].astype("datetime64[D]")
        days = np.unique(day)
        for name, baseline in baselines.items():
            olderr = np.where(mask, np.abs(baseline - observed), 0)
            newerr = np.where(mask, np.abs(chosen - observed), 0)
            daily = np.array(
                [
                    [olderr[day == d].sum(), newerr[day == d].sum(), mask[day == d].sum()]
                    for d in days
                ]
            )
            indices = np.random.default_rng(170219).integers(len(days), size=(20000, len(days)))
            samples = daily[indices].sum(axis=1)
            percent = 100 * (1 - samples[:, 1] / samples[:, 0])
            row = {
                "horizon_minutes": minutes,
                "baseline": name,
                "baseline_mae_mph": float(olderr.sum() / mask.sum()),
                "new_mae_mph": float(newerr.sum() / mask.sum()),
                "reduction_pct": float(100 * (1 - newerr.sum() / olderr.sum())),
                "paired_day_block_ci95_pct": np.quantile(percent, [0.025, 0.975]).tolist(),
                "calendar_days": len(days),
                "valid_targets": int(mask.sum()),
            }
            comparisons.append(row)
            print(row, flush=True)
        for j, sensor in enumerate(sensors[:4]):
            previews.append(
                {
                    "sensor": sensor,
                    "horizon_minutes": minutes,
                    "model": study["selected_on_validation"],
                    "points": [
                        {
                            "timestamp": str(times[targets[test]][i]),
                            "actual": float(observed[i, j]) if mask[i, j] else None,
                            "predicted": float(chosen[i, j]),
                            "persistence": float(history[i, j, -1]),
                        }
                        for i in range(min(288, len(chosen)))
                    ],
                }
            )
    record["paired_analysis"] = comparisons
    record["analysis_source_sha256"] = sha(__file__)
    record["preview"] = previews
    record["preview_selection"] = (
        "First four sensors in source order, first 288 chronological held-out origins; not selected for error"
    )
    record["uncertainty_method"] = (
        "20000 paired full-calendar-day bootstrap resamples; all sensors in the same temporal block; remaining day dependence and external replication limitations"
    )
    target.write_text(json.dumps(record, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
