"""Separated, reproducible experiments. Synthetic scores are never field accuracy."""

import json
import platform
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config, db
from .schemas import SimulationConfig
from .simulation import optimize

FEATURES = [
    "ttc_s",
    "minimum_separation_m",
    "relative_speed_mps",
    "angle_rad",
    "vulnerable",
    "min_acceleration",
    "nearby_count",
]


def save(name, result):
    config.ARTIFACTS.mkdir(exist_ok=True, parents=True)
    result = {
        "generated_at": db.now(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        **result,
    }
    (config.ARTIFACTS / f"{name}.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    return result


def generate_conflicts(seed, count=4000):
    """Sample noisy observed features; labels come from hidden accelerated trajectories."""
    rng = np.random.default_rng(seed)
    horizon = rng.uniform(0.2, 8, count)
    true_separation = rng.uniform(0, 8, count)
    speed = rng.uniform(0.5, 20, count)
    angle = rng.uniform(0, np.pi, count)
    vulnerable = rng.binomial(1, 0.25, count)
    acceleration = rng.normal(-0.5, 2.5, count)
    density = rng.integers(1, 35, count)
    # Future hidden displacement differs from constant-velocity observed separation.
    future_separation = np.abs(
        true_separation + 0.08 * acceleration * horizon**2 + rng.normal(0, 0.6, count)
    )
    labels = (
        (future_separation < (1.5 + vulnerable * 0.8)) & (horizon < 4.5) & (speed > 2)
    ).astype(int)
    features = np.column_stack(
        [
            np.clip(horizon + rng.normal(0, 0.25, count), 0, 10),
            np.maximum(0, true_separation + rng.normal(0, 0.4, count)),
            speed,
            angle,
            vulnerable,
            acceleration + rng.normal(0, 0.5, count),
            density,
        ]
    )
    return features, labels


def calibration_error(y, probability, bins=10):
    result = 0
    for i in range(bins):
        mask = (probability >= i / bins) & (
            (probability < (i + 1) / bins) if i < bins - 1 else (probability <= 1)
        )
        if mask.any():
            result += float(mask.mean()) * abs(float(y[mask].mean() - probability[mask].mean()))
    return result


def benchmark_risk():
    train_x, train_y = generate_conflicts(1001, 6000)
    val_x, val_y = generate_conflicts(2002, 2000)
    test_x, test_y = generate_conflicts(3003, 3000)
    models = {
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=400, random_state=42)
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=120, max_leaf_nodes=15, l2_regularization=2, random_state=42
        ),
    }
    results, fitted = {}, {}
    for name, model in models.items():
        start = time.perf_counter()
        model.fit(train_x, train_y)
        val = model.predict_proba(val_x)[:, 1]
        thresholds = np.linspace(0.1, 0.9, 33)
        threshold = float(max(thresholds, key=lambda threshold: f1_score(val_y, val >= threshold)))
        probability = model.predict_proba(test_x)[:, 1]
        predictions = probability >= threshold
        cm = confusion_matrix(test_y, predictions)
        results[name] = {
            "auroc": float(roc_auc_score(test_y, probability)),
            "auprc": float(average_precision_score(test_y, probability)),
            "precision": float(precision_score(test_y, predictions, zero_division=0)),
            "recall": float(recall_score(test_y, predictions)),
            "f1": float(f1_score(test_y, predictions)),
            "brier": float(brier_score_loss(test_y, probability)),
            "ece": calibration_error(test_y, probability),
            "threshold": threshold,
            "confusion_matrix": cm.tolist(),
            "false_alerts_per_1000_pairs": float(cm[0, 1] / len(test_y) * 1000),
            "false_alerts_per_hour": None,
            "train_evaluate_seconds": time.perf_counter() - start,
        }
        fitted[name] = model
    # Selection uses validation AUPRC, never the held-out test metric.
    selected = max(
        fitted,
        key=lambda name: average_precision_score(val_y, fitted[name].predict_proba(val_x)[:, 1]),
    )
    model_dir = config.ARTIFACTS / "models"
    model_dir.mkdir(exist_ok=True)
    joblib.dump(fitted[selected], model_dir / "risk.joblib")
    return save(
        "risk",
        {
            "scope": "Synthetic independent scenarios; not real near-miss labels or field accuracy",
            "features": FEATURES,
            "splits": {
                "train": {"seed": 1001, "n": 6000},
                "validation": {"seed": 2002, "n": 2000},
                "test": {"seed": 3003, "n": 3000},
            },
            "selected": selected,
            "models": results,
            "test_prevalence": float(test_y.mean()),
        },
    )


def traffic_series(seed, minutes=2880):
    rng = np.random.default_rng(seed)
    t = np.arange(minutes)
    mean = 15 + 7 * np.sin(2 * np.pi * t / 1440) + 3 * np.sin(2 * np.pi * t / 240)
    values = np.zeros(minutes)
    values[0] = mean[0]
    for i in range(1, minutes):
        values[i] = max(0, 0.7 * values[i - 1] + 0.3 * mean[i] + rng.normal(0, 2))
    return values


def forecast_features(series, horizon):
    rows, targets, origins = [], [], []
    for i in range(30, len(series) - horizon):
        history = series[i - 30 : i]
        rows.append(
            [
                history[-1],
                history[-2],
                history[-5],
                history.mean(),
                history[-5:].mean(),
                history.std(),
                np.sin(2 * np.pi * i / 1440),
                np.cos(2 * np.pi * i / 1440),
            ]
        )
        targets.append(series[i + horizon - 1])
        origins.append(i)
    return np.array(rows), np.array(targets), np.array(origins)


def benchmark_forecast():
    series = traffic_series(4444)
    results = {}
    for horizon in [5, 10, 15]:
        x, y, origins = forecast_features(series, horizon)
        # Purge the horizon around boundaries; all target times remain in their split.
        train = origins + horizon < 1728
        test = origins >= 2304
        model = HistGradientBoostingRegressor(
            max_iter=150, max_leaf_nodes=15, l2_regularization=3, random_state=42
        )
        model.fit(x[train], y[train])
        predictions = {
            "last_value": x[test, 0],
            "historical_mean": np.full(test.sum(), float(y[train].mean())),
            "moving_average": x[test, 4],
            "gradient_boosting": model.predict(x[test]),
        }
        scores = {}
        for name, prediction in predictions.items():
            actual = y[test]
            positive = actual >= 1
            scores[name] = {
                "mae": float(mean_absolute_error(actual, prediction)),
                "rmse": float(np.sqrt(mean_squared_error(actual, prediction))),
                "mape_pct": float(
                    np.mean(np.abs((actual[positive] - prediction[positive]) / actual[positive]))
                    * 100
                ),
                "mape_excludes_below": 1,
            }
        results[str(horizon)] = {
            "models": scores,
            "test_points": int(test.sum()),
            "preview": [
                {
                    "minute": int(origins[test][i]),
                    "actual": round(float(y[test][i]), 3),
                    **{name: round(float(values[i]), 3) for name, values in predictions.items()},
                }
                for i in range(0, min(150, test.sum()), 3)
            ],
        }
    model_dir = config.ARTIFACTS / "models"
    model_dir.mkdir(exist_ok=True)
    joblib.dump(model, model_dir / "forecast-15.joblib")
    return save(
        "forecast",
        {
            "scope": "Synthetic diurnal traffic series, 1-minute bins; these are experiment results, not forecasts for demo footage",
            "seed": 4444,
            "split": {
                "train_end": 1728,
                "validation_end": 2304,
                "test_start": 2304,
                "purge": "horizon around training boundary",
            },
            "horizons": results,
        },
    )


def benchmark_simulation(seeds=(42, 43, 44)):
    outputs = []
    for seed in seeds:
        result = optimize(SimulationConfig(seed=seed))
        outputs.append(
            {
                "seed": seed,
                "settings": result["settings"],
                "search": result["search"],
                "runs": [
                    {"policy": r["policy"], "greens": r["greens"], "metrics": r["metrics"]}
                    for r in result["runs"]
                ],
                "improvement_pct": result["improvement_pct"],
            }
        )
    reductions = [r["improvement_pct"]["delay"] for r in outputs]
    return save(
        "simulation",
        {
            "scope": "Seeded microscopic simulation, not a field trial; selection on separate tuning seeds",
            "runs": outputs,
            "mean_delay_reduction_pct": float(np.mean(reductions)),
            "delay_reduction_std_pct": float(np.std(reductions)),
            "seeds": list(seeds),
        },
    )


def benchmark_cv(dataset="coco8.yaml"):
    from ultralytics import YOLO

    model = YOLO(config.MODEL)
    metrics = model.val(
        data=dataset,
        imgsz=640,
        device=config.DEVICE,
        project=str(config.ARTIFACTS),
        name="cv-eval",
        exist_ok=True,
        plots=False,
        workers=0,
    )
    return save(
        "cv",
        {
            "scope": f"{dataset} validation split; COCO8 is a tiny integration smoke dataset, not traffic-domain accuracy",
            "model": config.MODEL,
            "dataset": dataset,
            "precision": float(metrics.box.mp),
            "recall": float(metrics.box.mr),
            "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map),
            "speed_ms": metrics.speed,
        },
    )


def evaluate_mot(gt_path: Path, prediction_path: Path, artifact_name="tracking"):
    """MOTChallenge CSV evaluation using TrackEval's official metrics implementation."""
    try:
        import trackeval
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional evaluator with 'pip install trackeval' first"
        ) from exc
    from scipy.optimize import linear_sum_assignment

    gt = np.loadtxt(gt_path, delimiter=",", ndmin=2)
    pred = np.loadtxt(prediction_path, delimiter=",", ndmin=2)
    if gt.shape[1] < 6 or pred.shape[1] < 6:
        raise ValueError("Expected MOT CSV: frame,id,x,y,w,h,...")
    gt = gt[gt[:, 6] > 0] if gt.shape[1] > 6 else gt
    gt_map = {value: i for i, value in enumerate(np.unique(gt[:, 1]))}
    pred_map = {value: i for i, value in enumerate(np.unique(pred[:, 1]))}
    data = {
        "num_timesteps": int(max(gt[:, 0].max(), pred[:, 0].max())),
        "num_gt_ids": len(gt_map),
        "num_tracker_ids": len(pred_map),
        "num_gt_dets": len(gt),
        "num_tracker_dets": len(pred),
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
    }
    for frame in range(1, data["num_timesteps"] + 1):
        a, b = gt[gt[:, 0] == frame], pred[pred[:, 0] == frame]
        scores = np.zeros((len(a), len(b)))
        for i, ga in enumerate(a):
            for j, pb in enumerate(b):
                x = max(0, min(ga[2] + ga[4], pb[2] + pb[4]) - max(ga[2], pb[2]))
                y = max(0, min(ga[3] + ga[5], pb[3] + pb[5]) - max(ga[3], pb[3]))
                intersection = x * y
                scores[i, j] = intersection / max(
                    ga[4] * ga[5] + pb[4] * pb[5] - intersection, 1e-8
                )
        data["gt_ids"].append(np.array([gt_map[v] for v in a[:, 1]], dtype=int))
        data["tracker_ids"].append(np.array([pred_map[v] for v in b[:, 1]], dtype=int))
        data["similarity_scores"].append(scores)
    # Assert matching feasibility before invoking the official evaluator.
    if data["similarity_scores"]:
        linear_sum_assignment(-data["similarity_scores"][0])
    result = {}
    for metric in [
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR(),
        trackeval.metrics.Identity(),
    ]:
        scores = metric.eval_sequence(data)
        for key in ["HOTA", "MOTA", "IDF1", "IDSW", "Frag"]:
            if key in scores:
                result[key] = float(np.mean(scores[key]))
    return save(
        artifact_name,
        {
            "scope": "Official TrackEval metrics on supplied MOT-format files; only report with dataset attribution",
            "ground_truth": gt_path.name,
            "predictions": prediction_path.name,
            "metrics": result,
        },
    )
