"""Paired day-block uncertainty; saved original predictions must match frozen scores."""

import json
from pathlib import Path

import joblib
import numpy as np
import tables
from atlas.city_network import sha
from atlas.evaluation.data import METR_SHA
from atlas.evaluation.forecasting import causal_fill, chronological_masks
from atlas.forecast_v3 import features
from threadpoolctl import threadpool_limits


def main():
    path = Path("datasets/metr-la/metr-la.h5")
    if sha(path) != METR_SHA:
        raise ValueError("Pinned source mismatch")
    original = json.loads(
        Path("artifacts/benchmarks/real_forecasting.json").read_text(encoding="utf-8")
    )
    record_path = Path("artifacts/cities/forecast-v3.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    with tables.open_file(path) as file:
        values = file.root.df.block0_values.read()
        times = file.root.df.axis1.read().astype("datetime64[ns]")
    train_end = int(len(values) * 0.7)
    test_begin = int(len(values) * 0.8)
    filled, valid = causal_fill(values, train_end)
    gaps = np.r_[0, np.cumsum(np.diff(times) != np.timedelta64(5, "m"))]
    context_path = Path("data/models/forecast-v3/context.npz")
    if sha(context_path) != record["runtime_context_sha256"]:
        raise ValueError("Feature context changed")
    with np.load(context_path, allow_pickle=False) as context:
        means = context["means"]
        adjacency = context["adjacency"]
    comparisons = []
    for minutes in (5, 15):
        h = minutes // 5
        origins = np.arange(6, len(values) - h + 1)
        targets = origins + h - 1
        keep = gaps[targets] - gaps[origins - 6] == 0
        origins, targets = origins[keep], targets[keep]
        test = chronological_masks(origins, h, train_end, test_begin, len(values))["test"]
        history = np.stack([filled[origins - i] for i in range(6, 0, -1)], axis=2)[test]
        observed = values[targets[test]]
        mask = valid[targets[test]]
        clock = (
            (times[origins[test] - 1] - times[origins[test] - 1].astype("datetime64[D]"))
            .astype("timedelta64[m]")
            .astype(float)
        )
        clock = np.broadcast_to(clock[:, None], history.shape[:2])
        frozen_features = np.stack(
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
        old_path = Path(f"artifacts/models/metr-la-forecast-{minutes}.joblib")
        study = next(h for h in record["results"] if h["horizon_minutes"] == minutes)
        candidate = next(m for m in study["models"] if m["selected_on_validation"])
        new_path = Path(f"data/models/forecast-v3/{candidate['model']}-{minutes}.joblib")
        if sha(new_path) != candidate["model_sha256"]:
            raise ValueError("New checkpoint changed")
        with threadpool_limits(limits=4):
            old = (
                joblib.load(old_path)
                .predict(frozen_features.reshape(-1, 8))
                .reshape(observed.shape)
            )
            new_x = features(history, times[origins[test] - 1], means, adjacency)
            new = (
                joblib.load(new_path)
                .predict(new_x.reshape(-1, new_x.shape[-1]))
                .reshape(observed.shape)
            )
        old_error = np.where(mask, np.abs(old - observed), 0)
        new_error = np.where(mask, np.abs(new - observed), 0)
        old_mae = float(old_error.sum() / mask.sum())
        new_mae = float(new_error.sum() / mask.sum())
        if not np.isclose(
            old_mae,
            original["metrics"]["horizons"][str(minutes)]["atlas_gradient_boosting"]["mae"],
            atol=1e-10,
            rtol=0,
        ) or not np.isclose(new_mae, candidate["metrics"]["mae"], atol=1e-10, rtol=0):
            raise ValueError("Saved checkpoint predictions do not reproduce published scores")
        day = times[targets[test]].astype("datetime64[D]")
        days = np.unique(day)
        daily = np.array(
            [
                [old_error[day == d].sum(), new_error[day == d].sum(), mask[day == d].sum()]
                for d in days
            ]
        )
        indices = np.random.default_rng(170219).integers(len(days), size=(20000, len(days)))
        samples = daily[indices].sum(axis=1)
        delta = (samples[:, 0] - samples[:, 1]) / samples[:, 2]
        percent = 100 * (1 - samples[:, 1] / samples[:, 0])
        comparisons.append(
            {
                "horizon_minutes": minutes,
                "original_mae_mph": old_mae,
                "new_mae_mph": new_mae,
                "mae_reduction_pct": 100 * (1 - new_mae / old_mae),
                "paired_day_block_difference_ci95_mph": np.quantile(delta, [0.025, 0.975]).tolist(),
                "paired_day_block_reduction_ci95_pct": np.quantile(
                    percent, [0.025, 0.975]
                ).tolist(),
                "calendar_days": len(days),
                "valid_targets": int(mask.sum()),
                "original_model_sha256": sha(old_path),
                "new_model_sha256": sha(new_path),
                "method": "20000 paired resamples of full observed test calendar days; all sensors share each time block",
                "qualification": "Repeated days may remain dependent; this CI does not establish cross-network transfer or external replication",
            }
        )
    record["paired_original_analysis"] = comparisons
    record["paired_analysis_source_sha256"] = sha(__file__)
    record_path.write_text(json.dumps(record, allow_nan=False), encoding="utf-8")
    for row in comparisons:
        print(
            row["horizon_minutes"],
            round(row["mae_reduction_pct"], 3),
            "% reduction; paired day-block CI",
            row["paired_day_block_reduction_ci95_pct"],
            flush=True,
        )


if __name__ == "__main__":
    main()
