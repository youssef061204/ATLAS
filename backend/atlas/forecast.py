import numpy as np


def forecast_from_metrics(metrics):
    if not metrics:
        return {
            "status": "insufficient_history",
            "reason": "No observations available",
            "predictions": [],
        }
    duration = metrics[-1]["t"] - metrics[0]["t"]
    if duration < 900:
        return {
            "status": "insufficient_history",
            "reason": f"{duration:.0f} s observed; at least 15 minutes required for a 5-minute forecast.",
            "predictions": [],
        }
    # 60-second causal bins. No model fitted on fabricated history.
    bins = {}
    for m in metrics:
        bins.setdefault(int(m["t"] // 60), []).append(m["vehicles"])
    values = [float(np.mean(v)) for v in bins.values()]
    value = float(np.mean(values[-5:]))
    dispersion = float(np.std(np.diff(values[-15:]))) if len(values) > 1 else 0
    return {
        "status": "ready",
        "model": "causal 5-bin moving average",
        "target": "active vehicles",
        "scope": "Baseline forecast; residual spread is exploratory, not calibrated coverage",
        "predictions": [
            {
                "horizon_minutes": h,
                "value": round(value, 2),
                "lower": max(0, round(value - 1.96 * dispersion * np.sqrt(h), 2)),
                "upper": round(value + 1.96 * dispersion * np.sqrt(h), 2),
            }
            for h in [5, 10, 15]
        ],
    }
