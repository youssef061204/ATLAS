"""Telemetry gaps must never become invented coordinates or sanitized metrics."""

import pytest
from atlas.evaluation.network_v4_runtime import sanitize


def test_unavailable_replay_location_retains_provenance_without_inventing_position():
    unavailable = {}
    actual = {
        "metrics": {"mean_delay_s": 12.5},
        "trace": [{"vehicles": [{"lon": float("inf"), "lat": 43.6}]}],
    }
    result = sanitize(actual, unavailable)
    assert result["metrics"] == actual["metrics"]
    assert result["trace"][0]["vehicles"][0] == {"lon": None, "lat": 43.6}
    assert unavailable == {"trace[0].vehicles[0].lon": "inf"}
    assert actual["trace"][0]["vehicles"][0]["lon"] == float("inf")


def test_invalid_measured_outcomes_fail_instead_of_becoming_missing_or_zero():
    with pytest.raises(ValueError, match="measured outcome"):
        sanitize({"metrics": {"mean_delay_s": float("nan")}}, {})
