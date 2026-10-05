"""Chronological METR-LA sensor evaluation, with causal missing-history handling."""

from importlib.metadata import version

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from atlas import config
from atlas.evaluation.artifacts import checksum, write_artifact
from atlas.evaluation.data import DATASETS, METR_REVISION, METR_SHA


def chronological_masks(origins, horizon_steps, train_end, validation_end, length):
    targets = origins + horizon_steps - 1
    return {
        "train": targets < train_end,
        "validation": (origins >= train_end) & (targets < validation_end),
        "test": (origins >= validation_end) & (targets < length),
    }


def causal_fill(values, train_end):
    values = np.asarray(values, dtype=float)
    valid = np.isfinite(values) & (values > 0)
    initial = np.nanmedian(np.where(valid[:train_end], values[:train_end], np.nan), axis=0)
    if not np.isfinite(initial).all():
        raise ValueError("A sensor has no valid training observations")
    filled = values.copy()
    previous = initial
    for row in range(len(values)):
        previous = np.where(valid[row], values[row], previous)
        filled[row] = previous
    return filled, valid


def forecast_scores(actual, predicted, valid):
    actual, predicted = np.asarray(actual)[valid], np.asarray(predicted)[valid]
    if not len(actual):
        raise ValueError("No valid forecast targets")
    error = predicted - actual
    mape = actual >= 5
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape_pct": float(np.mean(np.abs(error[mape]) / actual[mape]) * 100)
        if mape.any()
        else None,
        "smape_pct": float(
            np.mean(2 * np.abs(error) / np.maximum(np.abs(actual) + np.abs(predicted), 1e-8)) * 100
        ),
        "valid_targets": len(actual),
        "mape_targets": int(mape.sum()),
        "unit": "mph",
        "mape_min_target_mph": 5,
    }


def evaluate_forecasting(max_train_rows=200000):
    import tables

    path = DATASETS / "metr-la" / "metr-la.h5"
    if checksum(path) != METR_SHA:
        raise ValueError("METR-LA checksum differs from the pinned source")
    # Direct fixed-format arrays avoid legacy pandas HDF attribute incompatibilities.
    with tables.open_file(path) as source:
        values = source.root.df.block0_values.read()
        timestamps = source.root.df.axis1.read().astype("datetime64[ns]")
        sensors = [x.decode() for x in source.root.df.axis0.read()]
        columns = [x.decode() for x in source.root.df.block0_items.read()]
    if (
        sensors != columns
        or len(timestamps) != len(values)
        or not np.all(np.diff(timestamps) > np.timedelta64(0, "ns"))
    ):
        raise ValueError("Invalid sensor/time alignment")
    length, sensor_count = values.shape
    train_end, validation_end = int(length * 0.7), int(length * 0.8)
    filled, valid = causal_fill(values, train_end)
    interval = np.timedelta64(5, "m")
    gap_prefix = np.r_[0, np.cumsum(np.diff(timestamps) != interval)]
    historical_mean = np.array(
        [values[:train_end, j][valid[:train_end, j]].mean() for j in range(sensor_count)]
    )
    horizons, predictions_by_horizon = {}, {}
    model_dir = config.ARTIFACTS / "models"
    model_dir.mkdir(exist_ok=True)
    for horizon_minutes in [5, 10, 15]:
        horizon = horizon_minutes // 5
        origins = np.arange(6, length - horizon + 1)
        targets = origins + horizon - 1
        continuous = gap_prefix[targets] - gap_prefix[origins - 6] == 0
        origins, targets = origins[continuous], targets[continuous]
        history = np.stack([filled[origins - i] for i in range(6, 0, -1)], axis=2)
        minutes = (
            (timestamps[origins - 1] - timestamps[origins - 1].astype("datetime64[D]"))
            .astype("timedelta64[m]")
            .astype(float)
        )
        clock = np.broadcast_to(minutes[:, None], (len(origins), sensor_count))
        features = np.stack(
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
        masks = chronological_masks(origins, horizon, train_end, validation_end, length)
        train_x = features[masks["train"]].reshape(-1, 8)
        train_y = values[targets[masks["train"]]].ravel()
        train_valid = valid[targets[masks["train"]]].ravel()
        choices = np.flatnonzero(train_valid)
        rng = np.random.default_rng(42)
        if len(choices) > max_train_rows:
            choices = np.sort(rng.choice(choices, max_train_rows, replace=False))
        model = HistGradientBoostingRegressor(
            max_iter=150, max_leaf_nodes=15, l2_regularization=3, random_state=42
        )
        with threadpool_limits(limits=4):
            model.fit(train_x[choices], train_y[choices])
            test_x = features[masks["test"]]
            gradient = model.predict(test_x.reshape(-1, 8)).reshape(-1, sensor_count)
        actual = values[targets[masks["test"]]]
        actual_valid = valid[targets[masks["test"]]]
        test_history = history[masks["test"]]
        predictions = {
            "persistence": test_history[:, :, -1],
            "historical_mean": np.broadcast_to(historical_mean, actual.shape),
            "moving_average_3bin": test_history[:, :, -3:].mean(axis=2),
            "atlas_current_5bin": test_history[:, :, -5:].mean(axis=2),
            "atlas_gradient_boosting": gradient,
        }
        scores = {
            name: forecast_scores(actual, prediction, actual_valid)
            for name, prediction in predictions.items()
        }
        test_times = timestamps[targets[masks["test"]]]
        preview = [
            {
                "timestamp": str(test_times[i]),
                "actual": float(actual[i, 0]) if actual_valid[i, 0] else None,
                **{name: float(p[i, 0]) for name, p in predictions.items()},
            }
            for i in range(min(288, len(actual)))
        ]
        horizons[str(horizon_minutes)] = {
            "models": scores,
            "train_sensor_targets": int(train_valid.sum()),
            "model_train_rows": len(choices),
            "validation_origins": int(masks["validation"].sum()),
            "test_origins": int(masks["test"].sum()),
            "per_sensor_mae": {
                sensor: forecast_scores(actual[:, j], gradient[:, j], actual_valid[:, j])["mae"]
                for j, sensor in enumerate(sensors)
            },
            "preview_sensor": sensors[0],
            "preview": preview,
        }
        predictions_by_horizon[str(horizon_minutes)] = (actual, gradient, actual_valid)
        joblib.dump(model, model_dir / f"metr-la-forecast-{horizon_minutes}.joblib")
        print(
            f"METR-LA {horizon_minutes} min: persistence MAE={scores['persistence']['mae']:.3f}, ATLAS ML MAE={scores['atlas_gradient_boosting']['mae']:.3f}",
            flush=True,
        )
    artifact = write_artifact(
        "real_forecasting",
        benchmark_type="forecasting",
        data_provenance="real",
        dataset="METR-LA",
        dataset_version=METR_REVISION,
        model="ATLAS causal 5-bin moving average + histogram gradient boosting",
        seed=42,
        split={
            "method": "chronological 70/10/20 percent of source timestamps",
            "train": [str(timestamps[0]), str(timestamps[train_end - 1])],
            "validation": [str(timestamps[train_end]), str(timestamps[validation_end - 1])],
            "test": [str(timestamps[validation_end]), str(timestamps[-1])],
            "train_end_index": train_end,
            "validation_end_index": validation_end,
        },
        metrics={
            "horizons": {h: data["models"] for h, data in horizons.items()},
            "sensors": sensor_count,
            "timestamps": length,
        },
        scope="Real highway speed observations in mph; all 207 sensors. Temporal univariate models, not a graph-network benchmark or intersection-count forecasting validation.",
        methodology={
            "source_sha256": METR_SHA,
            "interval_minutes": 5,
            "lookback_minutes": 30,
            "missing_history": "causal forward fill; initial missing values use training-only sensor medians",
            "target_mask": "finite speed > 0; MAPE restricted to >=5 mph",
            "gaps": "windows crossing non-five-minute timestamp intervals excluded",
            "purge": "targets crossing split boundary excluded",
            "fit": "Fixed synthetic-suite histogram-gradient-boosting hyperparameters; retrained on real training data, maximum 200000 seeded pooled sensor rows",
            "validation": "Reserved chronological partition, unused for hyperparameter tuning",
            "current_runtime_model": "Existing five-bin smoother applied at native five-minute cadence (25-minute history); not silently called a five-minute lookback",
            "sensor_dependency": "Pooled univariate rows; no sensor IDs, adjacency, future measurements, or test-based selection",
            "sklearn": version("scikit-learn"),
        },
        results={"horizons": horizons},
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory = config.ARTIFACTS / "benchmarks" / "plots"
    directory.mkdir(exist_ok=True)
    for h, data in horizons.items():
        rows = data["preview"]
        fig, ax = plt.subplots(figsize=(12, 4))
        x = np.arange(len(rows)) * 5
        for name, label in [
            ("actual", "Measured speed"),
            ("persistence", "Persistence"),
            ("atlas_gradient_boosting", "ATLAS gradient boosting"),
        ]:
            ax.plot(
                x,
                [np.nan if row[name] is None else row[name] for row in rows],
                label=label,
                linewidth=1.2,
            )
        ax.set(
            xlabel="Minutes into chronological test period",
            ylabel="Speed (mph)",
            title=f"METR-LA sensor {data['preview_sensor']} · {h}-minute horizon",
        )
        ax.legend()
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(directory / f"metr-la-{h}min.png", dpi=160)
        plt.close(fig)
    return artifact
