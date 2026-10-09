"""Validation-selected classical graph-context experiment; frozen evidence untouched."""

import json
import pickle
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import psutil
import tables
from atlas.cities import now
from atlas.city_network import sha
from atlas.evaluation.data import METR_SHA
from atlas.evaluation.forecasting import causal_fill, chronological_masks, forecast_scores
from atlas.forecast_v3 import features
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


def main():
    protocol_path = Path("docs/forecast-v3-protocol.json")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    path = Path("datasets/metr-la/metr-la.h5")
    graph_path = Path("datasets/metr-la/adj_mx.pkl")
    if sha(path) != METR_SHA or sha(graph_path) != protocol["adjacency_sha256"]:
        raise ValueError("Pinned input checksum mismatch")
    # Explicit trusted, checksum-pinned DCRNN research input; never an uploaded pickle.
    with graph_path.open("rb") as stream:
        graph_ids, _, adjacency = pickle.load(stream, encoding="latin1")
    with tables.open_file(path) as source:
        values = source.root.df.block0_values.read()
        timestamps = source.root.df.axis1.read().astype("datetime64[ns]")
        sensor_ids = [x.decode() for x in source.root.df.axis0.read()]
    graph_ids = [str(x) for x in graph_ids]
    index = [graph_ids.index(s) for s in sensor_ids]
    adjacency = adjacency[np.ix_(index, index)]
    train_end, test_begin = int(len(values) * 0.7), int(len(values) * 0.8)
    filled, valid = causal_fill(values, train_end)
    means = np.array(
        [values[:train_end, j][valid[:train_end, j]].mean() for j in range(values.shape[1])]
    )
    gap = np.r_[0, np.cumsum(np.diff(timestamps) != np.timedelta64(5, "m"))]
    all_results = []
    preview = []
    model_dir = Path("data/models/forecast-v3")
    model_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with threadpool_limits(limits=4):
        for minutes in protocol["horizons_minutes"]:
            horizon = minutes // 5
            origins = np.arange(6, len(values) - horizon + 1)
            targets = origins + horizon - 1
            keep = gap[targets] - gap[origins - 6] == 0
            origins, targets = origins[keep], targets[keep]
            history = np.stack([filled[origins - i] for i in range(6, 0, -1)], axis=2)
            masks = chronological_masks(origins, horizon, train_end, test_begin, len(values))
            candidates = []
            for name in ("temporal_context", "graph_context"):
                x = features(
                    history,
                    timestamps[origins - 1],
                    means,
                    adjacency if name == "graph_context" else None,
                )
                eligible = np.flatnonzero(valid[targets[masks["train"]]].ravel())
                choices = np.sort(
                    np.random.default_rng(42).choice(
                        eligible, min(len(eligible), protocol["max_train_rows"]), replace=False
                    )
                )
                model = HistGradientBoostingRegressor(**protocol["model"])
                tick = time.perf_counter()
                model.fit(
                    x[masks["train"]].reshape(-1, x.shape[-1])[choices],
                    values[targets[masks["train"]]].ravel()[choices],
                )
                elapsed = time.perf_counter() - tick
                validation = model.predict(x[masks["validation"]].reshape(-1, x.shape[-1])).reshape(
                    -1, len(sensor_ids)
                )
                score = forecast_scores(
                    values[targets[masks["validation"]]],
                    validation,
                    valid[targets[masks["validation"]]],
                )
                candidates.append((score["mae"], name, model, x, elapsed))
                print(minutes, name, "validation MAE", round(score["mae"], 5), flush=True)
            chosen = min(candidates, key=lambda v: v[0])[1]
            rows = []
            for validation_mae, name, model, x, train_seconds in candidates:
                test_x = x[masks["test"]]
                tick = time.perf_counter()
                predictions = model.predict(test_x.reshape(-1, x.shape[-1])).reshape(
                    -1, len(sensor_ids)
                )
                inference_seconds = time.perf_counter() - tick
                score = forecast_scores(
                    values[targets[masks["test"]]], predictions, valid[targets[masks["test"]]]
                )
                timings = []
                for row in test_x[:100]:
                    tick = time.perf_counter()
                    model.predict(row)
                    timings.append((time.perf_counter() - tick) * 1000)
                model_path = model_dir / f"{name}-{minutes}.joblib"
                joblib.dump(model, model_path)
                rows.append(
                    {
                        "model": name,
                        "selected_on_validation": name == chosen,
                        "validation_mae_mph": validation_mae,
                        "metrics": score,
                        "training_seconds": train_seconds,
                        "batch_inference_seconds": inference_seconds,
                        "all_207_sensor_latency_ms_p50": float(np.percentile(timings, 50)),
                        "all_207_sensor_latency_ms_p95": float(np.percentile(timings, 95)),
                        "model_bytes": model_path.stat().st_size,
                        "model_sha256": sha(model_path),
                        "train_rows": len(choices),
                        "features": x.shape[-1],
                    }
                )
                print(minutes, name, "test MAE", round(score["mae"], 5), flush=True)
                if name == chosen:
                    preview_actual = values[targets[masks["test"]]]
                    preview_valid = valid[targets[masks["test"]]]
                    preview_history = history[masks["test"]]
                    preview_times = timestamps[targets[masks["test"]]]
                    for j, sensor in enumerate(sensor_ids):
                        preview.append(
                            {
                                "sensor": sensor,
                                "horizon_minutes": minutes,
                                "model": name,
                                "points": [
                                    {
                                        "timestamp": str(preview_times[i]),
                                        "actual": float(preview_actual[i, j])
                                        if preview_valid[i, j]
                                        else None,
                                        "predicted": float(predictions[i, j]),
                                        "persistence": float(preview_history[i, j, -1]),
                                    }
                                    for i in range(min(288, len(predictions)))
                                ],
                            }
                        )
            persistence = forecast_scores(
                values[targets[masks["test"]]],
                history[masks["test"]][:, :, -1],
                valid[targets[masks["test"]]],
            )
            all_results.append(
                {
                    "horizon_minutes": minutes,
                    "selected": chosen,
                    "models": rows,
                    "persistence": persistence,
                    "test_origins": int(masks["test"].sum()),
                }
            )
    result = {
        "experiment_id": "metr-la-graph-context-v3-01",
        "recorded_at": now(),
        "protocol_sha256": sha(protocol_path),
        "dataset_sha256": METR_SHA,
        "adjacency_sha256": sha(graph_path),
        "source_sha256": sha("backend/atlas/forecast_v3.py"),
        "evaluation_sha256": sha(__file__),
        "splits": {
            "train_end": train_end,
            "test_begin": test_begin,
            "test_first": str(timestamps[test_begin]),
            "test_last": str(timestamps[-1]),
        },
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_threads": 4,
            "rss_mib_at_end": psutil.Process().memory_info().rss / 2**20,
        },
        "wall_seconds": time.perf_counter() - start,
        "results": all_results,
        "limitations": [
            "Shared historical ATLAS test period; external independent replication outstanding",
            "Graph-assisted boosting, not a GNN",
            "METR-LA speeds; not city camera queue forecasts",
            "Both candidates reported; deployment selection uses validation only",
        ],
        "preview": preview,
    }
    Path("artifacts/cities/forecast-v3.json").write_text(
        json.dumps(result, allow_nan=False), encoding="utf-8"
    )
    print("completed", result["experiment_id"], flush=True)


if __name__ == "__main__":
    main()
