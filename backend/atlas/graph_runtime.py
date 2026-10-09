"""Checksum-verified local GNN inference; weights-only loading, no online learning."""

import json
import time
from functools import lru_cache

import numpy as np
import torch

from atlas import config
from atlas.city_network import sha
from atlas.forecast_v3 import features
from atlas.graph_forecast import GraphForecaster


@lru_cache(maxsize=6)
def load_checkpoint(path, digest):
    # Caller verifies actual bytes on each request, even for cached versions.
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    sensors = checkpoint["sensor_ids"]
    model = GraphForecaster(
        np.zeros((len(sensors), len(sensors))), graph="directional_gnn" in str(path)
    )
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval(), checkpoint


def predict_graph(history, timestamp, horizon_minutes=5):
    started = time.perf_counter()
    record = json.loads(
        (config.ARTIFACTS / "cities/graph-forecast.json").read_text(encoding="utf-8")
    )
    study = next((h for h in record["results"] if h["horizon_minutes"] == horizon_minutes), None)
    if not study:
        raise ValueError("Unsupported evaluated neural forecast horizon")
    selected = next(m for m in study["models"] if m["model"] == study["selected_on_validation"])
    path = config.DATA / "models/graph-forecast" / f"{selected['model']}-{horizon_minutes}.pt"
    context_path = config.DATA / "models/forecast-v3/context.npz"
    classical = json.loads(
        (config.ARTIFACTS / "cities/forecast-v3.json").read_text(encoding="utf-8")
    )
    if not path.exists() or not context_path.exists():
        raise ValueError("Native evaluated neural checkpoint/context unavailable")
    if (
        sha(path) != selected["checkpoint_sha256"]
        or sha(context_path) != classical["runtime_context_sha256"]
    ):
        raise ValueError("Neural checkpoint/context checksum mismatch; refusing inference")
    model, checkpoint = load_checkpoint(str(path), selected["checkpoint_sha256"])
    with np.load(context_path, allow_pickle=False) as context:
        means = context["means"]
        if context["sensor_ids"].tolist() != checkpoint["sensor_ids"]:
            raise ValueError("Neural sensor order mismatch")
    x = np.asarray(history, dtype=float).copy()
    if x.shape != (207, 6) or np.any(np.isinf(x)):
        raise ValueError("Expected 207 sensors by six chronological speed samples")
    missing = ~np.isfinite(x) | (x <= 0)
    previous = means.copy()
    for j in range(6):
        previous = np.where(missing[:, j], previous, x[:, j])
        x[:, j] = previous
    ready = features(x[None], np.array([timestamp], dtype="datetime64[ns]"), means)
    standardized = (torch.tensor(ready) - checkpoint["mean"]) / checkpoint["scale"]
    with torch.inference_mode():
        predictions = model(standardized).numpy()[0] * 10 + x[:, -1]
    return {
        "experiment_id": record["experiment_id"],
        "model": selected["model"],
        "model_sha256": selected["checkpoint_sha256"],
        "sensor_ids": checkpoint["sensor_ids"],
        "predicted_mph": predictions.tolist(),
        "horizon_minutes": horizon_minutes,
        "unit": "mph",
        "missing_history_fraction": float(missing.mean()),
        "end_to_end_inference_ms": (time.perf_counter() - started) * 1000,
        "scope": "METR-LA highway sensor domain only; neural research candidate, no city camera demand mapping",
        "confidence": "Predictive intervals and cross-network calibration unavailable; high missingness requires review",
    }
