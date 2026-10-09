import pytest
from atlas.visual_flow import CrossingCounter


def test_counts_finite_crossing_once_per_direction_and_tolerates_deadband():
    c = CrossingCounter([0.1, 0.5], [0.9, 0.5])
    assert c.update(0, [{"id": 1, "point": [0.4, 0.45]}]) == []
    assert c.update(0.04, [{"id": 1, "point": [0.4, 0.501]}]) == []
    assert c.update(0.08, [{"id": 1, "point": [0.4, 0.55]}])[0]["direction"] == "positive"
    assert c.update(0.12, [{"id": 1, "point": [0.4, 0.45]}])[0]["direction"] == "negative"
    assert c.update(0.16, [{"id": 1, "point": [0.4, 0.55]}]) == []


def test_line_extension_outside_gate_and_discontinuous_tracks_do_not_count():
    c = CrossingCounter([0.2, 0.5], [0.8, 0.5])
    c.update(0, [{"id": 1, "point": [0.95, 0.4]}, {"id": 2, "point": [0.5, 0.4]}])
    assert c.update(0.04, [{"id": 1, "point": [0.95, 0.6]}]) == []
    assert c.update(1, [{"id": 2, "point": [0.5, 0.6]}]) == []
    with pytest.raises(ValueError, match="snapshots"):
        c.update(2, [], continuous=False)
    with pytest.raises(ValueError, match="strictly"):
        c.update(0.5, [])
