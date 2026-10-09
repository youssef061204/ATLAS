"""Causal graph-context features for the METR-LA research forecaster.

This is graph-assisted gradient boosting, not a graph neural network. Road
weights are static; sensor statistics must be fitted on training observations.
"""

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=6)
def _checkpoint(path, digest):
    import joblib

    # Caller verifies the actual bytes before using this version-keyed cache.
    return joblib.load(path)


def predict_evaluated(history, timestamp, horizon_minutes=5):
    """Trusted local checkpoints only; domain is fixed METR-LA sensor order."""
    import json
    import time

    from threadpoolctl import threadpool_limits

    from atlas import config
    from atlas.city_network import sha

    started = time.perf_counter()
    report = json.loads((config.ARTIFACTS / "cities/forecast-v3.json").read_text(encoding="utf-8"))
    study = next((h for h in report["results"] if h["horizon_minutes"] == horizon_minutes), None)
    if not study:
        raise ValueError("Unsupported evaluated forecast horizon")
    model = next(m for m in study["models"] if m["selected_on_validation"])
    root = config.DATA / "models/forecast-v3"
    path = root / f"{model['model']}-{horizon_minutes}.joblib"
    context_path = root / "context.npz"
    if not path.exists() or not context_path.exists():
        raise ValueError(
            "Evaluated model checkpoint unavailable; prepare native forecasting runtime"
        )
    if sha(path) != model["model_sha256"] or sha(context_path) != report["runtime_context_sha256"]:
        raise ValueError("Model/context checksum mismatch; refusing inference")
    with np.load(context_path, allow_pickle=False) as context:
        x = np.asarray(history, dtype=float)
        means = context["means"]
        adjacency = context["adjacency"]
        sensors = context["sensor_ids"].tolist()
    if x.shape != (len(sensors), 6) or np.any(np.isinf(x)):
        raise ValueError(
            "Expected 207 sensors by six chronological samples in documented source order"
        )
    missing = ~np.isfinite(x) | (x <= 0)
    previous = means.copy()
    for j in range(6):
        previous = np.where(missing[:, j], previous, x[:, j])
        x[:, j] = previous
    with threadpool_limits(limits=4):
        ready = features(
            x[None, :, :],
            np.array([timestamp], dtype="datetime64[ns]"),
            means,
            adjacency if model["model"] == "graph_context" else None,
        )[0]
        prediction = _checkpoint(str(path), model["model_sha256"]).predict(ready)
    return {
        "experiment_id": report["experiment_id"],
        "model": model["model"],
        "model_sha256": model["model_sha256"],
        "horizon_minutes": horizon_minutes,
        "unit": "mph",
        "sensor_ids": sensors,
        "predicted_mph": prediction.tolist(),
        "missing_history_fraction": float(missing.mean()),
        "end_to_end_inference_ms": (time.perf_counter() - started) * 1000,
        "confidence": "Independent uncertainty calibration unavailable for this model",
        "scope": "METR-LA highway sensors only; not city camera queues or arrival rates",
    }


def graph_weights(adjacency):
    a = np.asarray(adjacency, dtype=float).copy()
    if a.ndim != 2 or a.shape[0] != a.shape[1] or not np.all(np.isfinite(a)) or np.any(a < 0):
        raise ValueError("Invalid nonnegative square road adjacency")
    np.fill_diagonal(a, 0)
    total = a.sum(axis=1, keepdims=True)
    return np.divide(a, total, out=np.zeros_like(a), where=total > 0).astype(np.float32)


def features(history, timestamps, means, adjacency=None):
    """Six past samples ending at the origin, never the future target."""
    history = np.asarray(history, dtype=np.float32)
    means = np.asarray(means, dtype=np.float32)
    if history.ndim != 3 or history.shape[-1] != 6 or means.shape != (history.shape[1],):
        raise ValueError("Expected origins × sensors × six historical samples")
    times = np.asarray(timestamps, dtype="datetime64[ns]")
    if len(times) != len(history) or not np.all(np.isfinite(history)):
        raise ValueError("Invalid causal history/time alignment")
    clock = (times - times.astype("datetime64[D]")).astype("timedelta64[m]").astype(float)
    weekday = (times.astype("datetime64[D]").astype(int) + 3) % 7

    def broadcast(x):
        return np.broadcast_to(x[:, None], history.shape[:2])

    columns = [history[:, :, j] for j in range(6)] + [
        history.mean(axis=2),
        history[:, :, -3:].mean(axis=2),
        history.std(axis=2),
        history[:, :, -1] - history[:, :, -2],
        np.broadcast_to(means, history.shape[:2]),
        broadcast(np.sin(2 * np.pi * clock / 1440)),
        broadcast(np.cos(2 * np.pi * clock / 1440)),
        broadcast(weekday),
    ]
    if adjacency is not None:
        weights = graph_weights(adjacency)
        if weights.shape != (history.shape[1], history.shape[1]):
            raise ValueError("Graph/sensor alignment mismatch")
        incoming = graph_weights(np.asarray(adjacency).T)
        recent = history[:, :, -3:].mean(axis=2)
        columns += [
            history[:, :, -1] @ weights.T,
            recent @ weights.T,
            history[:, :, -1] @ incoming.T,
            recent @ incoming.T,
        ]
    return np.stack(columns, axis=2).astype(np.float32)
