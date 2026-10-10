"""Prevent target normalization leakage and verify causal-input abstention."""

import numpy as np
from atlas.city_forecast_v5 import (
    SourceInvariantForecaster,
    features,
    interval_metrics,
    normalized_targets,
)


def rows(city="toronto", multiplier=1):
    return [
        {
            "city": city,
            "time": f"2025-01-{day:02d}T12:00:00",
            "date": f"2025-01-{day:02d}",
            "interval_seconds": 900,
            "history_flow_vph": [40 * multiplier, 44 * multiplier, 48 * multiplier],
            "actual": 13 * multiplier,
            "neighbor_flow_vph": [0, 0, 0],
            "neighbor_sites": 0,
        }
        for day in range(1, 21)
    ]


def test_representation_and_residual_targets_are_scale_invariant():
    assert np.allclose(features(rows()), features(rows(multiplier=100)))
    assert np.allclose(normalized_targets(rows()), normalized_targets(rows(multiplier=100)))


def test_target_labels_do_not_influence_features_or_predictions():
    model = SourceInvariantForecaster(rows(), "ridge_1")
    target = rows("austin", multiplier=50)
    before, _ = model.predict(target)
    for row in target:
        row["actual"] = 99999999
    after, _ = model.predict(target)
    assert np.array_equal(before, after)


def test_unseen_causal_drift_reverts_to_persistence():
    model = SourceInvariantForecaster(rows(), "ridge_1")
    target = rows("calgary")
    target[0]["history_flow_vph"] = [10, 10, 1000]
    predicted, drift = model.predict(target)
    assert drift[0]
    assert predicted[0] == 250


def test_interval_score_penalizes_narrow_missed_forecasts():
    target = rows()
    exact = np.asarray([13] * 20)
    assert interval_metrics(target, exact, 0)["mean_interval_score"] == 0
    missed = interval_metrics(target, exact - 10, 0)
    assert missed["empirical_coverage"] == 0
    assert missed["mean_interval_score"] == 200
