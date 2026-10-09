"""Causal uncertainty-aware count estimation, calibration and interval forecasting."""

from dataclasses import dataclass

import numpy as np


@dataclass
class CountFilter:
    mean: float = 0
    variance: float = 100
    process_variance_per_second: float = 0.2
    timestamp: float | None = None

    def __post_init__(self):
        if (
            not np.isfinite(self.mean)
            or self.mean < 0
            or not np.isfinite(self.variance)
            or self.variance <= 0
            or not np.isfinite(self.process_variance_per_second)
            or self.process_variance_per_second < 0
        ):
            raise ValueError("Invalid filter prior or process noise")

    def update(self, timestamp, count=None, measurement_variance=9):
        if not np.isfinite(timestamp) or self.timestamp is not None and timestamp <= self.timestamp:
            raise ValueError("Observations must have strictly increasing finite timestamps")
        if not np.isfinite(measurement_variance) or measurement_variance <= 0:
            raise ValueError("Measurement variance must be positive")
        dt = 0 if self.timestamp is None else timestamp - self.timestamp
        self.variance += self.process_variance_per_second * dt
        if count is not None:
            if not np.isfinite(count) or count < 0:
                raise ValueError("Count must be finite and nonnegative")
            gain = self.variance / (self.variance + measurement_variance)
            self.mean += gain * (count - self.mean)
            self.variance *= 1 - gain
        self.timestamp = timestamp
        radius = 1.96 * np.sqrt(self.variance)
        return {
            "mean": float(self.mean),
            "interval95": [max(0, float(self.mean - radius)), float(self.mean + radius)],
            "provenance_class": "estimated_state",
            "timestamp": timestamp,
            "measurement_available": count is not None,
            "assumptions": "Scalar random-walk Gaussian count filter; not a calibrated queue or demand estimator",
        }


def calibrate_scale(predicted, measured, holdout_predicted, holdout_measured):
    """Nonnegative least-squares scalar demand scale; heldout arrays stay separate."""
    x, y, hx, hy = [
        np.asarray(v, dtype=float)
        for v in (predicted, measured, holdout_predicted, holdout_measured)
    ]
    if len(x) < 3 or len(hx) < 2 or x.shape != y.shape or hx.shape != hy.shape:
        raise ValueError("Need paired training and independent validation observations")
    if (
        any(not np.all(np.isfinite(v)) or np.any(v < 0) for v in (x, y, hx, hy))
        or np.dot(x, x) == 0
    ):
        raise ValueError("Invalid count calibration data")
    scale = max(0, float(np.dot(x, y) / np.dot(x, x)))
    return {
        "scale": scale,
        "train_mae": float(np.mean(np.abs(scale * x - y))),
        "validation_mae": float(np.mean(np.abs(scale * hx - hy))),
        "train_samples": len(x),
        "validation_samples": len(hx),
        "model": "nonnegative least-squares scalar",
        "provenance_class": "calibration_result",
    }


def rolling_intervals(series, horizons=(1, 3, 6), warmup=60, calibration=40):
    """Rolling origin EWMA/persistence; calibration residuals precede each origin.

    Horizons are samples, not minutes unless caller establishes a 5-min cadence.
    No fitted model or residual ever consumes the future evaluation target.
    """
    y = np.asarray(series, dtype=float)
    if y.ndim != 1 or not np.all(np.isfinite(y)) or len(y) <= warmup + max(horizons):
        raise ValueError("Insufficient finite chronological observations")
    results = []
    for h in horizons:
        if h < 1:
            raise ValueError("Horizon must be positive")
        for model in ("persistence", "ewma"):
            errors, hits, widths = [], [], []
            residuals = []
            pending = {}
            mean = y[0]
            for t in range(len(y) - h):
                mean = 0.3 * y[t] + 0.7 * mean
                if t in pending:
                    residuals.append(abs(pending.pop(t) - y[t]))
                forecast = y[t] if model == "persistence" else mean
                pending[t + h] = forecast
                if t < warmup or len(residuals) < calibration:
                    continue
                recent = np.array(residuals[-calibration:])
                rank = min(len(recent), int(np.ceil((len(recent) + 1) * 0.9)))
                radius = float(np.sort(recent)[rank - 1])
                error = float(forecast - y[t + h])
                errors.append(error)
                hits.append(abs(error) <= radius)
                widths.append(2 * radius)
            results.append(
                {
                    "model": model,
                    "horizon_samples": h,
                    "samples": len(errors),
                    "mae": float(np.mean(np.abs(errors))),
                    "rmse": float(np.sqrt(np.mean(np.square(errors)))),
                    "coverage90": float(np.mean(hits)),
                    "calibration_error": abs(float(np.mean(hits)) - 0.9),
                    "mean_interval_width": float(np.mean(widths)),
                }
            )
    return results


class IncidentDetector:
    """Robust rolling median/MAD anomaly detector, not collision recognition."""

    def __init__(self, window=30, threshold=4):
        self.window, self.threshold, self.history = window, threshold, []

    def update(self, value):
        if not np.isfinite(value) or value < 0:
            raise ValueError("Invalid traffic observation")
        median = float(np.median(self.history)) if self.history else value
        mad = float(np.median(np.abs(np.array(self.history) - median))) if self.history else 0
        score = (value - median) / max(1, 1.4826 * mad)
        flagged = len(self.history) >= 10 and score >= self.threshold
        self.history = (self.history + [value])[-self.window :]
        return {
            "anomaly": bool(flagged),
            "score": float(score),
            "kind": "queue_surge" if flagged else "normal",
            "baseline": median,
            "limitation": "Statistical anomaly; not confirmed incident",
        }
