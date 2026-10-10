"""Scientific failure cases, temporal independence and identifiable estimation."""

from datetime import datetime, timedelta

import numpy as np
import pytest
from atlas.calibration_v5 import (
    DemandProfile,
    chronological_split,
    count_metrics,
    date_bootstrap_mae,
    estimate_nonnegative_demand,
)


def records():
    return [
        {
            "site_id": "a",
            "direction": "n",
            "interval_seconds": 900,
            "observed_at": (datetime(2025, 1, 1) + timedelta(days=d, minutes=15 * s)).isoformat(),
            "count": 10 + s,
        }
        for d in range(20)
        for s in range(4)
    ]


def test_verified_identifiable_weighted_inverse_recovers_demands():
    result = estimate_nonnegative_demand(
        [[1, 0], [0, 1], [1, 1]], [20, 30, 50], [1, 1, 4], mapping_verified=True
    )
    assert np.allclose(result["demand"], [20, 30])
    assert result["rank"] == 2


def test_unidentifiable_and_unmapped_inverse_is_refused():
    with pytest.raises(ValueError, match="Unidentifiable"):
        estimate_nonnegative_demand([[1, 1], [2, 2]], [10, 20], [1, 1], mapping_verified=True)
    with pytest.raises(ValueError, match="Verified"):
        estimate_nonnegative_demand([[1]], [10], [1], mapping_verified=False)
    with pytest.raises(ValueError, match="invalid"):
        estimate_nonnegative_demand([[1]], [10], [0], mapping_verified=True)


def test_final_counts_cannot_influence_training_profile():
    split, dates = chronological_split(records())
    assert max(dates["calibration"]) < min(dates["validation"]) < min(dates["final"])
    model = DemandProfile(split["calibration"], 8)
    before = [model.predict(r) for r in split["final"]]
    for r in split["final"]:
        r["count"] = 999999
    assert before == [model.predict(r) for r in split["final"]]
    assert model.predict({**split["final"][0], "site_id": "missing"}) is None


def test_duplicate_counts_and_insufficient_dates_do_not_create_evidence():
    with pytest.raises(ValueError, match="Duplicate"):
        DemandProfile([records()[0], records()[0]], 0)
    with pytest.raises(ValueError, match="Three"):
        chronological_split(records()[:4])
    short = records()[:4]
    assert date_bootstrap_mae(short, [10] * 4)["interval"] is None


def test_flow_units_coverage_and_unsupported_state_metrics():
    rows = records()[:2]
    result = count_metrics(rows, [8, None])
    assert result["count_mae"] == 2
    assert result["flow_mae_vph"] == 8
    assert result["coverage_fraction"] == 0.5
    assert result["physical_queue_error"] is None
    assert count_metrics(rows, [None, None])["rows"] == 0
    with pytest.raises(ValueError, match="Invalid predicted"):
        count_metrics(rows, [-1, 0])
