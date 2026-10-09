import numpy as np
import pytest
from atlas.scene import PlanarCalibration, SceneRegion, VisualQueueEstimator, assign_detections


def test_planar_projection_uses_correspondences_and_independent_holdout():
    image = [[0, 0], [1, 0], [1, 1], [0, 1]]
    world = [[0, 0], [10, 0], [10, 20], [0, 20]]
    model = PlanarCalibration(image, world)
    np.testing.assert_allclose(
        model.project([[0.5, 0.5], [0.2, 0.8]]), [[5, 10], [2, 16]], atol=1e-9
    )
    assert model.holdout([[0.5, 0.5], [0.2, 0.8]], [[6, 10], [2, 17]])[
        "mean_error_m"
    ] == pytest.approx(1)
    assert model.status.endswith("not_independently_validated")
    with pytest.raises(ValueError, match="span"):
        PlanarCalibration([[0, 0], [0.1, 0], [0.2, 0], [0.3, 0]], world)


def test_region_rejects_invalid_geometry_and_assigns_bottom_centers():
    fields = {
        "city": "toronto",
        "camera_id": "one",
        "observation_id": "observed",
        "road_id": "actual",
        "name": "Approach",
    }
    region = SceneRegion(**fields, polygon=[[0, 0], [0.5, 0], [0.5, 1], [0, 1]])
    detections = [
        {"box_normalized": [0.1, 0.1, 0.3, 0.3], "class": "car"},
        {"box_normalized": [0.6, 0.1, 0.9, 0.3], "class": "car"},
    ]
    assert assign_detections(region, detections) == detections[:1]
    with pytest.raises(ValueError):
        SceneRegion(**fields, polygon=[[0, 0], [1, 1], [0, 1], [1, 0]])


def test_visual_queue_requires_continuity_and_stationary_dwell_not_raw_counts():
    polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
    calibration = PlanarCalibration(polygon, [[0, 0], [10, 0], [10, 20], [0, 20]])
    queue = VisualQueueEstimator(polygon, calibration, [[0, 0], [10, 0]])
    for i in range(31):
        result = queue.update(
            i / 25,
            [
                {"id": "stopped", "point": [0.5, 0.5]},
                {"id": "moving", "point": [0.2, 0.1 + i * 0.005]},
            ],
        )
    assert result["queue_candidate_vehicles"] == 0
    for i in range(31, 61):
        result = queue.update(
            i / 25,
            [
                {"id": "stopped", "point": [0.5, 0.5]},
                {"id": "moving", "point": [0.2, 0.1 + i * 0.005]},
            ],
        )
    assert result["queue_candidate_vehicles"] == 1 and result[
        "queue_candidate_extent_m"
    ] == pytest.approx(10)
    result = queue.update(4, [{"id": "stopped", "point": [0.5, 0.5]}])
    assert result["queue_candidate_vehicles"] == 0
    with pytest.raises(ValueError, match="snapshot"):
        queue.update(5, [], continuous=False)
