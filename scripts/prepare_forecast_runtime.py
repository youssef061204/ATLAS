"""Prepare training-only feature context for the evaluated native forecasting service."""

import json
import pickle
from pathlib import Path

import numpy as np
import tables
from atlas.city_network import sha
from atlas.evaluation.data import METR_SHA
from atlas.evaluation.forecasting import causal_fill


def main():
    report_path = Path("artifacts/cities/forecast-v3.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    path = Path("datasets/metr-la/metr-la.h5")
    graph = Path("datasets/metr-la/adj_mx.pkl")
    if sha(path) != METR_SHA or sha(graph) != report["adjacency_sha256"]:
        raise ValueError("Pinned feature context sources changed")
    with graph.open("rb") as stream:
        graph_ids, _, adjacency = pickle.load(stream, encoding="latin1")
    with tables.open_file(path) as source:
        values = source.root.df.block0_values.read()
        sensors = [s.decode() for s in source.root.df.axis0.read()]
    train_end = int(len(values) * 0.7)
    _, valid = causal_fill(values, train_end)
    means = np.array(
        [values[:train_end, j][valid[:train_end, j]].mean() for j in range(len(sensors))]
    )
    indices = [list(map(str, graph_ids)).index(s) for s in sensors]
    output = Path("data/models/forecast-v3/context.npz")
    np.savez(
        output,
        means=means,
        adjacency=adjacency[np.ix_(indices, indices)],
        sensor_ids=np.array(sensors),
    )
    report["runtime_context_sha256"] = sha(output)
    report_path.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
    print("Prepared training-only context for", len(sensors), "sensors")


if __name__ == "__main__":
    main()
