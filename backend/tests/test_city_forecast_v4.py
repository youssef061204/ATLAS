"""Protect temporal separation and absence semantics of actual-source forecasting."""

from datetime import datetime, timedelta

import numpy as np
from atlas.city_forecast_v4 import TrainingScale, conformal_radius, samples


def document():
    rows = []
    for day in range(10):
        for site in ("a", "b"):
            for slot in range(12):
                stamp = datetime(2025, 1, 1) + timedelta(days=day, minutes=15 * slot)
                rows.append(
                    {
                        "site_id": site,
                        "observed_at": stamp.isoformat(),
                        "interval_seconds": 900,
                        "count": 10 + slot,
                        "direction": "north",
                    }
                )
    return {
        "city": "toronto",
        "sites": {"a": {"lat": 43.65, "lon": -79.38}, "b": {"lat": 43.651, "lon": -79.38}},
        "records": rows,
    }


def test_whole_date_splits_and_strict_causal_graph():
    rows, info = samples(document())
    dates = info["split_dates"]
    assert set(dates["train"]).isdisjoint(dates["test"])
    assert max(dates["train"]) < min(dates["validation"]) < min(dates["test"])
    assert all(r["neighbor_sites"] == 1 for r in rows)
    first = rows[0]
    assert first["actual"] == 13
    assert first["history_flow_vph"] == [40, 44, 48]


def test_missing_bins_are_not_zero_filled_or_interpolated():
    value = document()
    value["records"] = [
        r
        for r in value["records"]
        if not (r["site_id"] == "a" and r["observed_at"] == "2025-01-01T01:00:00")
    ]
    rows, _ = samples(value)
    assert not any(r["site_id"] == "a" and "2025-01-01T01:" in r["time"] for r in rows)
    assert any(r["site_id"] == "a" and r["time"] == "2025-01-01T02:00:00" for r in rows)


def test_training_normalization_does_not_read_test_targets():
    rows, _ = samples(document())
    train = [r for r in rows if r["split"] == "train"]
    scale = TrainingScale(train)
    before = scale.features([rows[-1]])
    rows[-1]["actual"] = 99999999
    assert np.array_equal(before, scale.features([rows[-1]]))
    assert conformal_radius([1, 2], np.array([1, 2])) is None
    assert conformal_radius([1] * 19, np.zeros(19)) == 1
