from __future__ import annotations

import pytest
from atlas.turn_location_v8 import classify_turn


def test_turn_location_uses_official_marker_proximity_and_withholds_unsupported() -> None:
    markers = {88: (0, 0), 89: (500, 0), 90: (1000, 0)}
    assert classify_turn((520, 0), markers)["supported_signal"] == 89
    far = classify_turn((520, 500), markers)
    assert far["supported_signal"] is None
    assert far["nearest_signal"] == 89
    with pytest.raises(ValueError, match="positive"):
        classify_turn((0, 0), markers, 0)
