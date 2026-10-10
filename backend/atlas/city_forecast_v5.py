"""Causal scale-invariant city forecasting with source-only transfer safeguards."""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

TIMEZONES = {
    "toronto": "America/Toronto",
    "london": "Europe/London",
    "seattle": "America/Los_Angeles",
    "austin": "America/Chicago",
    "calgary": "America/Edmonton",
}


def causal_scale(rows):
    # The floor is a fixed physical rate, never a target-city normalization statistic.
    return np.maximum(np.mean([r["history_flow_vph"] for r in rows], axis=1), 4.0)


def features(rows, geographic=False):
    history = np.asarray([r["history_flow_vph"] for r in rows], dtype=float)
    scale = causal_scale(rows)
    ratios = history / scale[:, None]
    clock = []
    for row in rows:
        time = datetime.fromisoformat(row["time"])
        if time.tzinfo is not None:
            time = time.astimezone(ZoneInfo(TIMEZONES[row["city"]]))
        hour = time.hour + time.minute / 60
        clock.append(
            [
                np.sin(hour * 2 * np.pi / 24),
                np.cos(hour * 2 * np.pi / 24),
                np.sin(time.weekday() * 2 * np.pi / 7),
                np.cos(time.weekday() * 2 * np.pi / 7),
                np.log(row["interval_seconds"] / 900),
            ]
        )
    result = np.column_stack(
        [ratios, ratios[:, 2] - ratios[:, 1], ratios[:, 1] - ratios[:, 0], clock]
    )
    if geographic:
        # Proximity evidence only. Zero-shot default does not require this modality.
        result = np.column_stack(
            [
                result,
                [
                    r["neighbor_flow_vph"][-1] / s if r["neighbor_sites"] else 0
                    for r, s in zip(rows, scale, strict=True)
                ],
                [bool(r["neighbor_sites"]) for r in rows],
            ]
        )
    return result


def persistence(rows):
    return np.asarray([r["history_flow_vph"][-1] * r["interval_seconds"] / 3600 for r in rows])


def normalized_targets(rows):
    actual = np.asarray([r["actual"] * 3600 / r["interval_seconds"] for r in rows])
    last = np.asarray([r["history_flow_vph"][-1] for r in rows])
    return (actual - last) / causal_scale(rows)


class SourceInvariantForecaster:
    def __init__(self, rows, candidate, geographic=False):
        self.candidate, self.geographic = candidate, geographic
        x = features(rows, geographic)
        self.lower, self.upper = np.quantile(x[:, :5], [0.005, 0.995], axis=0)
        self.model = None
        if candidate.startswith("ridge_"):
            self.model = Ridge(alpha=float(candidate.split("_")[1]))
        elif candidate == "boosting":
            self.model = HistGradientBoostingRegressor(
                max_iter=100,
                max_leaf_nodes=8,
                min_samples_leaf=30,
                l2_regularization=10,
                random_state=51002,
            )
        elif candidate != "persistence":
            raise ValueError("Unknown registered forecasting candidate")
        if self.model is not None:
            city_sizes = {
                city: sum(r["city"] == city for r in rows) for city in {r["city"] for r in rows}
            }
            weights = np.asarray(
                [len(rows) / (len(city_sizes) * city_sizes[r["city"]]) for r in rows]
            )
            self.model.fit(x, normalized_targets(rows), sample_weight=weights)

    def predict(self, rows):
        x = features(rows, self.geographic)
        drift = np.any((x[:, :5] < self.lower - 1e-9) | (x[:, :5] > self.upper + 1e-9), axis=1)
        base = persistence(rows)
        if self.model is None:
            return base, drift
        scale_count = causal_scale(rows) * np.asarray([r["interval_seconds"] / 3600 for r in rows])
        residual = self.model.predict(x)
        # Source-trained extrapolations are bounded and abstain on causal-input drift.
        residual = np.clip(residual, -1, 1)
        prediction = np.maximum(0, base + residual * scale_count)
        prediction[drift] = base[drift]
        return prediction, drift


def interval_radius(rows, predictions, coverage=0.9):
    scale_count = causal_scale(rows) * np.asarray([r["interval_seconds"] / 3600 for r in rows])
    residual = np.abs(np.asarray([r["actual"] for r in rows]) - predictions) / scale_count
    if len(residual) < 19:
        return None
    probability = min(1.0, np.ceil((len(residual) + 1) * coverage) / len(residual))
    return float(np.quantile(residual, probability, method="higher"))


def interval_metrics(rows, predictions, radius, alpha=0.1):
    if radius is None:
        return {"status": "insufficient validation residuals"}
    scale_count = causal_scale(rows) * np.asarray([r["interval_seconds"] / 3600 for r in rows])
    lower, upper = (
        np.maximum(0, predictions - radius * scale_count),
        predictions + radius * scale_count,
    )
    actual = np.asarray([r["actual"] for r in rows])
    score = (
        upper
        - lower
        + 2 / alpha * np.maximum(lower - actual, 0)
        + 2 / alpha * np.maximum(actual - upper, 0)
    )
    return {
        "nominal_coverage": 1 - alpha,
        "empirical_coverage": float(np.mean((actual >= lower) & (actual <= upper))),
        "mean_width_count": float(np.mean(upper - lower)),
        "mean_interval_score": float(np.mean(score)),
        "scope": "validation-calibrated intervals; temporal/source shift can invalidate nominal coverage",
    }
