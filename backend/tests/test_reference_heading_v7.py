import numpy as np
import pytest
from atlas.reference_heading_v7 import cardinal_heading


def test_stationary_and_first_seen_east_west_are_not_northbound():
    result = cardinal_heading([1, 2, 3, 4], np.full((4, 2), np.nan))
    np.testing.assert_array_equal(result, [[1, 0], [0, 1], [-1, 0], [0, -1]])


def test_actual_past_displacement_overrides_cardinal_fallback():
    result = cardinal_heading([1, 4], [[0, -5], [0.1, 0.2]])
    np.testing.assert_array_equal(result, [[0, -1], [0, -1]])
    with pytest.raises(ValueError, match="Unknown"):
        cardinal_heading([0], [[0, 0]])
