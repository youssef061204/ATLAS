"""Predeclared CPU neural graph versus matched temporal MLP, same frozen holdout."""

import copy
import json
import pickle
import platform
import time
from pathlib import Path

import numpy as np
import psutil
import tables
import torch
from atlas.cities import now
from atlas.city_network import sha
from atlas.evaluation.forecasting import causal_fill, chronological_masks, forecast_scores
from atlas.forecast_v3 import features
from atlas.graph_forecast import GraphForecaster


def main():
    protocol_path = Path("docs/graph-forecast-protocol.json")
    p = json.loads(protocol_path.read_text())
    path, graph_path = Path("datasets/metr-la/metr-la.h5"), Path("datasets/metr-la/adj_mx.pkl")
    if sha(path) != p["dataset_sha256"] or sha(graph_path) != p["adjacency_sha256"]:
        raise ValueError("Pinned graph/dataset mismatch")
    with graph_path.open("rb") as stream:
        ids, _, adjacency = pickle.load(stream, encoding="latin1")
    with tables.open_file(path) as source:
        values = source.root.df.block0_values.read()
        times = source.root.df.axis1.read().astype("datetime64[ns]")
        sensors = [s.decode() for s in source.root.df.axis0.read()]
    order = [list(map(str, ids)).index(s) for s in sensors]
    adjacency = adjacency[np.ix_(order, order)]
    train_end, val_end = int(len(values) * 0.7), int(len(values) * 0.8)
    filled, valid = causal_fill(values, train_end)
    means = np.array(
        [values[:train_end, j][valid[:train_end, j]].mean() for j in range(len(sensors))]
    )
    gap = np.r_[0, np.cumsum(np.diff(times) != np.timedelta64(5, "m"))]
    torch.set_num_threads(p["threads"])
    torch.use_deterministic_algorithms(True)
    output = []
    model_dir = Path("data/models/graph-forecast")
    model_dir.mkdir(parents=True, exist_ok=True)
    for minutes in p["horizons_minutes"]:
        horizon = minutes // 5
        origins = np.arange(6, len(values) - horizon + 1)
        targets = origins + horizon - 1
        keep = gap[targets] - gap[origins - 6] == 0
        origins, targets = origins[keep], targets[keep]
        masks = chronological_masks(origins, horizon, train_end, val_end, len(values))
        history = np.stack([filled[origins - i] for i in range(6, 0, -1)], axis=2)
        x = features(history, times[origins - 1], means)
        choices = np.sort(
            np.random.default_rng(p["seed"]).choice(
                np.flatnonzero(masks["train"]),
                min(p["max_training_origins"], int(masks["train"].sum())),
                replace=False,
            )
        )
        mean = x[choices].mean(axis=(0, 1))
        scale = x[choices].std(axis=(0, 1))
        scale = np.maximum(scale, 1e-3)
        x = (x - mean) / scale
        train_x = torch.tensor(x[choices])
        train_y = torch.tensor(
            (values[targets[choices]] - history[choices, :, -1]) / 10, dtype=torch.float32
        )
        train_valid = torch.tensor(valid[targets[choices]])
        records = []
        for candidate in p["candidates"]:
            torch.manual_seed(p["seed"])
            model = GraphForecaster(
                adjacency, hidden=p["hidden"], graph=candidate == "directional_gnn"
            )
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=p["learning_rate"], weight_decay=p["weight_decay"]
            )

            def predict(indices, model=model, x=x, history=history):
                predictions = []
                model.eval()
                with torch.inference_mode():
                    for start in range(0, len(indices), 128):
                        batch = indices[start : start + 128]
                        predictions.append(
                            model(torch.tensor(x[batch])).numpy() * 10 + history[batch, :, -1]
                        )
                return np.concatenate(predictions)

            best, state, epoch_log = float("inf"), None, []
            started = time.perf_counter()
            for epoch in range(p["epochs"]):
                model.train()
                for batch in torch.randperm(len(choices)).split(p["batch_size"]):
                    optimizer.zero_grad(set_to_none=True)
                    prediction = model(train_x[batch])
                    loss = torch.abs(prediction - train_y[batch])[train_valid[batch]].mean()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                    optimizer.step()
                val_indices = np.flatnonzero(masks["validation"])
                score = forecast_scores(
                    values[targets[val_indices]], predict(val_indices), valid[targets[val_indices]]
                )["mae"]
                epoch_log.append({"epoch": epoch + 1, "validation_mae_mph": score})
                if score < best:
                    best, state = score, copy.deepcopy(model.state_dict())
                print(minutes, candidate, epoch + 1, "validation", round(score, 4), flush=True)
            training_seconds = time.perf_counter() - started
            model.load_state_dict(state)
            test_indices = np.flatnonzero(masks["test"])
            score = forecast_scores(
                values[targets[test_indices]], predict(test_indices), valid[targets[test_indices]]
            )
            latency = []
            with torch.inference_mode():
                for i in test_indices[:100]:
                    tick = time.perf_counter()
                    model(torch.tensor(x[i : i + 1]))
                    latency.append((time.perf_counter() - tick) * 1000)
            checkpoint = model_dir / f"{candidate}-{minutes}.pt"
            torch.save(
                {
                    "state_dict": state,
                    "mean": torch.tensor(mean),
                    "scale": torch.tensor(scale),
                    "sensor_ids": sensors,
                    "graph_sha256": p["adjacency_sha256"],
                },
                checkpoint,
            )
            records.append(
                {
                    "model": candidate,
                    "validation_mae_mph": best,
                    "epochs": epoch_log,
                    "metrics": score,
                    "training_seconds": training_seconds,
                    "parameters": sum(v.numel() for v in model.parameters()),
                    "checkpoint_bytes": checkpoint.stat().st_size,
                    "checkpoint_sha256": sha(checkpoint),
                    "all_207_sensor_forward_ms_p95": float(np.percentile(latency, 95)),
                    "training_origins": len(choices),
                    "training_valid_targets": int(train_valid.sum()),
                }
            )
            print(minutes, candidate, "test MAE", round(score["mae"], 5), flush=True)
        chosen = min(records, key=lambda r: r["validation_mae_mph"])["model"]
        output.append(
            {"horizon_minutes": minutes, "selected_on_validation": chosen, "models": records}
        )
    result = {
        "experiment_id": p["experiment_id"],
        "recorded_at": now(),
        "protocol_sha256": sha(protocol_path),
        "model_source_sha256": sha("backend/atlas/graph_forecast.py"),
        "evaluation_source_sha256": sha(__file__),
        "dataset_sha256": sha(path),
        "adjacency_sha256": sha(graph_path),
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "cpu_threads": p["threads"],
            "rss_mib_at_end": psutil.Process().memory_info().rss / 2**20,
        },
        "results": output,
        "limitations": [
            "One fixed neural configuration and seed; not an exhaustive GNN comparison",
            "Shared historical test period; independent external replication pending",
            "Training origin sampling produces more target rows than HGB's 200000-row cap; report cost, not equal-budget superiority",
            "Highway speeds only; not city snapshot queues",
            "Forward latency excludes features/checksum/HTTP",
        ],
    }
    Path("artifacts/cities/graph-forecast.json").write_text(
        json.dumps(result, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
