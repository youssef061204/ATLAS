from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from atlas.assimilation_v5 import Measurement, assimilate

NOW = datetime(2026, 10, 10, tzinfo=UTC)


def measurement(identity="d", modality="detector", value=20, variance=4):
    return Measurement(
        identity,
        modality,
        "arrival_flow_vph",
        value,
        variance,
        NOW,
        60,
        "road-a",
        True,
        correlation_group=identity,
        independent_group_verified=True,
    )


def fuse(rows, **kwargs):
    return assimilate(rows, now=NOW, metric="arrival_flow_vph", footprint_id="road-a", **kwargs)


def test_independent_compatible_measurements_reduce_conditional_variance():
    result = fuse([measurement(), measurement("c", "camera", value=22)])
    assert result["mean"] == 21
    assert result["variance"] == 2


def test_stale_partial_unmapped_and_static_image_counts_are_not_fused():
    invalid = [
        replace(measurement("old"), observed_at=NOW - timedelta(hours=1)),
        replace(measurement("partial"), spatial_coverage_fraction=0.5),
        replace(measurement("unmapped"), mapping_verified=False),
        replace(measurement("image"), metric="visible_vehicles"),
        replace(measurement("time"), observed_at=NOW.replace(tzinfo=None)),
    ]
    result = fuse(invalid)
    assert result["mean"] is None
    assert len(result["rejected_observations"]) == 5


def test_overlapping_or_unknown_dependence_does_not_invent_precision():
    a = replace(measurement("a"), independent_group_verified=False)
    b = replace(measurement("b"), independent_group_verified=False)
    assert fuse([a, b])["variance"] == 4
    assert fuse([measurement(), measurement()])["variance"] == 4


def test_disagreement_quarantines_camera_and_outage_propagates_uncertainty():
    result = fuse([measurement(), measurement("c", "camera", value=100)])
    assert result["used_observations"] == ["d"]
    assert result["sensor_disagreements"] == ["c"]
    outage = fuse([], prior_mean=20, prior_variance=4, elapsed_seconds=60)
    assert outage["mean"] == 20
    assert outage["variance"] == 64
    assert outage["mode"] == "prediction_only"
    with pytest.raises(ValueError, match="timezone"):
        assimilate([], now=NOW.replace(tzinfo=None), metric="queue_vehicles", footprint_id="a")
