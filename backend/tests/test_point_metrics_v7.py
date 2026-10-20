import pytest
from atlas.point_metrics_v7 import evaluate_points


def test_empty_reference_cohort_has_no_accuracy_estimate():
    report = evaluate_points({}, {0: [{"id": 1, "point": [0, 0]}]}, 0, 1)
    assert report["empty_reference_cohort"]
    assert report["reference_coverage"] is None
    assert report["matched_position_mae_m"] is None
    assert report["instantaneous_count"]["normalized_mae"] is None


def test_missing_observations_are_in_denominator_and_gaps_are_explicit():
    truth = {0: [{"id": 1, "point": [0, 0], "speed": 2}, {"id": 2, "point": [100, 0], "speed": 3}]}
    predictions = {0: [{"id": 7, "point": [1, 0], "speed": 1, "inferred": True}]}
    result = evaluate_points(truth, predictions, 0, 1)
    assert result["reference_coverage"] == 0.5
    assert result["matched_position_mae_m"] == 1
    assert result["matched_speed_mps"]["mae"] == 1
    assert result["actual_detector_observations"] == 0
    assert result["matched_inferred_observations"] == result["predicted_inferred_observations"] == 1
    assert result["instantaneous_count"]["normalized_mae"] == 0.5


def test_global_identity_score_penalizes_fragmentation():
    truth = {t: [{"id": 1, "point": [t, 0]}] for t in range(4)}
    prediction = {t: [{"id": t // 2, "point": [t, 0]}] for t in range(4)}
    result = evaluate_points(truth, prediction, 0, 4)
    assert result["reference_coverage"] == 1
    assert result["identity"]["IDF1"] == pytest.approx(0.5)
    assert result["sampled_assignment_id_changes"] == 1
