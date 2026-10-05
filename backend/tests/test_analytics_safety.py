import pytest
from atlas.analytics import TrajectoryEngine
from atlas.forecast import forecast_from_metrics
from atlas.geometry import Projection
from atlas.safety import SafetyEngine, closest_approach, segment_pet
from atlas.schemas import Calibration, Region


def detection(track=1, x=0):
    return {"id": track, "class": "car", "bbox": [x, 0, x + 10, 10], "confidence": 0.9}


def test_unique_tracks_and_stopped_queue_are_observation_derived():
    engine = TrajectoryEngine(Projection(None), [])
    for i in range(30):
        engine.update(i / 10, [detection()])
    assert engine.summary()["unique_tracks"] == 1
    assert engine.metrics[-1]["queue_length"] == 1
    assert engine.metrics[-1]["speed_unit"] == "px/s"
    assert engine.metrics[-1]["throughput"] == 0
    engine.update(3, [])
    assert engine.metrics[-1]["active_objects"] == 0


def test_approaching_and_diverging_ttc():
    ttc, distance, speed = closest_approach([0, 0], [5, 0], [10, 0], [-5, 0])
    assert ttc == pytest.approx(1)
    assert distance == 0
    assert speed == 10
    assert closest_approach([0, 0], [-5, 0], [10, 0], [5, 0])[0] < 0


def test_unverified_projection_preserves_pixel_motion_units():
    projection = Projection(
        Calibration(
            image=[(0, 0), (100, 0), (100, 100), (0, 100)],
            world=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )
    )
    engine = TrajectoryEngine(projection, [])
    for i in range(10):
        engine.update(i / 10, [detection(x=i)])
    assert engine.metrics[-1]["average_speed"] == pytest.approx(10)
    assert engine.metrics[-1]["speed_unit"] == "px/s"
    assert engine.metrics[-1]["queue_length"] == 0
    with pytest.raises(ValueError, match="enclose an area"):
        Region(id="invalid", kind="intersection", polygon=[(0, 0), (1, 0), (2, 0)])


def test_safety_requires_verified_metric_calibration_and_deduplicates():
    a = {
        "id": 1,
        "class": "car",
        "world": [0, 0],
        "velocity": [5, 0],
        "speed": 5,
        "acceleration": 0,
        "confidence": 0.9,
    }
    b = {**a, "id": 2, "class": "person", "world": [10, 0], "velocity": [-5, 0]}
    assert SafetyEngine(False).update(0, [a, b]) == []
    engine = SafetyEngine(True)
    assert len(engine.update(0, [a, b])) == 1
    assert engine.update(0.1, [a, b]) == []
    assert engine.events[0]["type"] == "vulnerable_road_user_conflict"


def test_forecast_refuses_to_extrapolate_a_short_demo():
    assert forecast_from_metrics([])["status"] == "insufficient_history"
    metrics = [{"t": t, "vehicles": 10} for t in range(30)]
    assert forecast_from_metrics(metrics)["predictions"] == []
    forecast = forecast_from_metrics([{"t": t, "vehicles": 10} for t in range(1000)])
    assert forecast["predictions"][0]["value"] == 10


def test_pet_interpolates_crossing_times_and_rejects_parallel_paths():
    a0, a1 = {"t": 0, "world": [-1, 0]}, {"t": 1, "world": [1, 0]}
    b0, b1 = {"t": 1, "world": [0, -1]}, {"t": 2, "world": [0, 1]}
    assert segment_pet(a0, a1, b0, b1) == pytest.approx(1)
    assert segment_pet(a0, a1, a0, a1) is None
