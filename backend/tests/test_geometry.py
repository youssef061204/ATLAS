import numpy as np
import pytest
from atlas.geometry import Projection, motion
from atlas.schemas import Calibration


def test_projection_matches_measured_control_points():
    calibration = Calibration(
        image=[(0, 0), (200, 0), (200, 100), (0, 100)],
        world=[(0, 0), (20, 0), (20, 10), (0, 10)],
        verified=True,
    )
    projection = Projection(calibration)
    assert np.allclose(projection.point(100, 50), [10, 5])
    assert projection.verified


def test_degenerate_calibration_rejected():
    calibration = Calibration(
        image=[(0, 0), (1, 1), (2, 2), (3, 3)], world=[(0, 0), (20, 0), (20, 10), (0, 10)]
    )
    with pytest.raises(ValueError, match="collinear"):
        Projection(calibration)


def test_timestamp_regression_handles_irregular_sampling():
    times = [0, 0.1, 0.3, 0.55, 0.7]
    points = [{"t": t, "world": [2 * t + 4, -3 * t + 7]} for t in times]
    assert np.allclose(motion(points), [2, -3])


def test_stationary_motion_and_duplicate_timestamps():
    assert motion([{"t": 1, "world": [4, 5]}] * 3) == (0, 0)
