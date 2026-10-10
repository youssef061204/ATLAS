"""Learn from actual SUMO transitions; unseen-city simulator truth remains authoritative."""

import json
import time
from pathlib import Path

import numpy as np
from atlas.cities import now
from atlas.city_network import sha
from atlas.learned_control_v4 import surrogate_features
from sklearn.ensemble import HistGradientBoostingRegressor


def main():
    path = Path("data/control-v4/transitions-dev.json")
    protocol_path = Path("docs/surrogate-v4-protocol.json")
    protocol = json.loads(protocol_path.read_text())
    episodes = [r for r in json.loads(path.read_text())["runs"] if r["policy"] == "original_mpc"]
    rows = []
    for heldout in ("toronto", "london", "seattle", "austin", "calgary"):
        train_x, train_y, test_x, test_y, persistence = [], [], [], [], []
        for run in episodes:
            for first, second in zip(run["trace"][:-1], run["trace"][1:], strict=True):
                if second["t"] - first["t"] != 5:
                    raise ValueError("Surrogate requires actual five-second transitions")
                if run["city"] == heldout:
                    test_x.append(surrogate_features(first))
                    test_y.append(second["queue"])
                    persistence.append(first["queue"])
                else:
                    train_x.append(surrogate_features(first))
                    train_y.append(second["queue"])
        if not test_y or not train_y:
            raise ValueError("Actual held-out-city transitions required")
        params = protocol["model"]
        model = HistGradientBoostingRegressor(
            max_iter=params["max_iter"],
            max_leaf_nodes=params["max_leaf_nodes"],
            l2_regularization=params["l2_regularization"],
            random_state=params["seed"],
            early_stopping=False,
        )
        started = time.perf_counter()
        model.fit(train_x, train_y)
        train_seconds = time.perf_counter() - started
        timings = []
        for _ in range(100):
            before = time.perf_counter()
            prediction = np.maximum(0, model.predict(test_x))
            timings.append((time.perf_counter() - before) * 1000)
        error = np.asarray(test_y) - prediction
        rows.append(
            {
                "held_out_city": heldout,
                "trained_cities": [
                    c for c in ("toronto", "london", "seattle", "austin", "calgary") if c != heldout
                ],
                "training_transitions": len(train_y),
                "test_transitions": len(test_y),
                "training_seconds": train_seconds,
                "queue_mae_vehicles": float(np.abs(error).mean()),
                "queue_rmse_vehicles": float(np.sqrt((error**2).mean())),
                "persistence_queue_mae_vehicles": float(
                    np.abs(np.asarray(test_y) - persistence).mean()
                ),
                "batch_inference_ms_p50": float(np.percentile(timings, 50)),
                "batch_inference_ms_p95": float(np.percentile(timings, 95)),
                "actual": test_y,
                "predicted": prediction.tolist(),
                "persistence": persistence,
                "promoted": False,
            }
        )
        print(
            heldout,
            "surrogate MAE",
            rows[-1]["queue_mae_vehicles"],
            "persistence",
            rows[-1]["persistence_queue_mae_vehicles"],
            flush=True,
        )
    result = {
        "experiment_id": protocol["experiment_id"],
        "recorded_at": now(),
        "protocol_sha256": sha(protocol_path),
        "training_input_sha256": sha(path),
        "source_sha256": sha(__file__),
        "feature_source_sha256": sha("backend/atlas/learned_control_v4.py"),
        "source_episodes": [
            {
                k: r[k]
                for k in (
                    "city",
                    "policy",
                    "seed",
                    "network_sha256",
                    "routes_sha256",
                    "harness_sha256",
                )
            }
            for r in episodes
        ],
        "rows": rows,
        "scope": protocol["scope"],
        "simulator_replacement": False,
        "actual_sumo_truth_preserved": True,
        "timing_scope": protocol["timing"],
    }
    Path("artifacts/cities/v4/surrogate.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
