"""New METR-LA 5/15/30-min interval evaluation; historical ML artifacts untouched."""

import json
import time
from pathlib import Path

import numpy as np
import tables
from atlas.cities import now
from atlas.city_network import sha
from atlas.evaluation.data import METR_SHA
from atlas.evaluation.forecasting import causal_fill
from atlas.probabilistic import causal_intervals


def main():
    path = Path("datasets/metr-la/metr-la.h5")
    if sha(path) != METR_SHA:
        raise ValueError("METR-LA source checksum mismatch")
    with tables.open_file(path) as file:
        values = file.root.df.block0_values.read()
        timestamps = file.root.df.axis1.read().astype("datetime64[ns]")
    train_end, test_begin = int(len(values) * 0.7), int(len(values) * 0.8)
    filled, valid = causal_fill(values, train_end)
    gap_prefix = np.r_[0, np.cumsum(np.diff(timestamps) != np.timedelta64(5, "m"))]
    results = []
    for h in (1, 3, 6):
        origins = np.arange(len(values) - h)
        continuous = gap_prefix[origins + h] == gap_prefix[origins]
        for model in ("persistence", "ewma"):
            tick = time.perf_counter()
            pred, radius = causal_intervals(filled, valid, continuous, h, model)
            elapsed = time.perf_counter() - tick
            selected = (
                (origins >= test_begin)[:, None]
                & continuous[:, None]
                & valid[h:]
                & np.isfinite(radius[:-h])
            )
            errors = pred[:-h][selected] - values[h:][selected]
            widths = radius[:-h][selected]
            coverage = float(np.mean(np.abs(errors) <= widths))
            results.append(
                {
                    "model": model,
                    "horizon_minutes": h * 5,
                    "sensor_count": values.shape[1],
                    "test_origin_begin": str(timestamps[test_begin]),
                    "test_targets": len(errors),
                    "mae_mph": float(np.abs(errors).mean()),
                    "rmse_mph": float(np.sqrt(np.mean(errors**2))),
                    "coverage90": coverage,
                    "calibration_error": abs(coverage - 0.9),
                    "mean_interval_width_mph": float(np.mean(2 * widths)),
                    "batch_evaluation_seconds": elapsed,
                    "method": "Rolling last 40 already-resolved residuals; finite-sample rank; minimum 30 valid calibration errors",
                }
            )
    Path("artifacts/cities/probabilistic-forecast.json").write_text(
        json.dumps(
            {
                "recorded_at": now(),
                "source_sha256": METR_SHA,
                "scope": "Independent METR-LA probabilistic baseline extension, not an upgraded neural predictor or five-city flow/queue forecast",
                "splits": {"train_end": train_end, "test_begin": test_begin},
                "results": results,
                "limitations": [
                    "Temporal dependence and regime shift invalidate distribution-free coverage guarantees",
                    "No weather/transit/incident covariates",
                    "Only speeds, not five-city queues or demand",
                ],
            },
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    for r in results:
        print(r["model"], r["horizon_minutes"], r["mae_mph"], r["coverage90"], flush=True)


if __name__ == "__main__":
    main()
