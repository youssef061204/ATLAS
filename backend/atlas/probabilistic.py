"""Vectorized causal rolling residual intervals, with no target-time leakage."""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def causal_intervals(values, valid, continuous, horizon, model="persistence", window=40):
    y = np.asarray(values, dtype=float)
    if y.ndim != 2 or y.shape != np.shape(valid) or len(y) < window + horizon or horizon < 1:
        raise ValueError("Invalid chronological sensor arrays")
    if not np.all(np.isfinite(y)) or model not in {"persistence", "ewma"}:
        raise ValueError("Invalid prediction model/data")
    pred = y.copy()
    if model == "ewma":
        for t in range(1, len(y)):
            pred[t] = 0.3 * y[t] + 0.7 * pred[t - 1]
    # At origin t, only forecasts whose targets are <= t have resolved.
    residual = np.full(y.shape, np.nan)
    errors = np.abs(pred[:-horizon] - y[horizon:])
    permitted = valid[horizon:] & np.asarray(continuous, dtype=bool)[:, None]
    residual[horizon:] = np.where(permitted, errors, np.nan)
    history = sliding_window_view(residual, window_shape=window, axis=0)
    count = np.isfinite(history).sum(axis=2)
    sorted_errors = np.sort(history, axis=2)
    ranks = np.minimum(count, np.ceil(0.9 * (count + 1))).astype(int) - 1
    radius = np.take_along_axis(sorted_errors, np.maximum(0, ranks)[..., None], axis=2)[..., 0]
    radius[count < 30] = np.nan
    full_radius = np.full(y.shape, np.nan)
    full_radius[window - 1 :] = radius
    return pred, full_radius
