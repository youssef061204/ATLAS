"""Causal graph-context features for the METR-LA research forecaster.

This is graph-assisted gradient boosting, not a graph neural network. Road
weights are static; sensor statistics must be fitted on training observations.
"""

import numpy as np


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
