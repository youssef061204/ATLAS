from atlas.physical_metrics_v7 import acceptance, birth_correspondence, physical_errors


def test_physical_error_is_not_censored_to_make_a_four_metre_gate_look_good():
    reference = {
        0: [{"id": 1, "point": [0, 0], "speed": 1}],
        10: [{"id": 1, "point": [1, 0], "speed": 1}],
    }
    entries = [{"id": "cv_7", "t": 0, "observed_world_m": [0, 0]}]
    mapping, diagnostic = birth_correspondence(entries, reference)
    assert diagnostic == {}
    result = physical_errors(
        mapping, reference, {1: [{"id": "cv_7", "point": [31, 0], "speed": 2}]}, 1, 2
    )
    assert result["uncapped_position_m"]["mae"] == 30
    assert result["within_4m_reference_coverage"] == 0
    assert result["native_presence_coverage"] == 1


def test_ambiguous_births_and_duplicate_admissions_are_not_extra_true_vehicles():
    entries = [{"id": f"cv_{i}", "t": 0, "observed_world_m": [0, 0]} for i in [1, 2]]
    mapping, diagnostics = birth_correspondence(entries, {0: [{"id": 1, "point": [0, 0]}]})
    assert len(mapping) == 1
    assert diagnostics["duplicate_admissions_for_reference_identity"] == 1
    mapping, diagnostics = birth_correspondence(
        entries[:1], {0: [{"id": 1, "point": [0, 0]}, {"id": 2, "point": [0.1, 0]}]}
    )
    assert mapping == {}
    assert diagnostics["ambiguous_birth_identity"] == 1


def test_missing_physical_truth_cannot_pass_acceptance():
    limits = {
        "count_normalized_mae_max": 0.2,
        "directional_flow_normalized_absolute_error_max": 0.2,
        "queue_count_mae_max_vehicles": 2,
        "matched_position_mae_max_m": 4,
        "matched_reference_coverage_min": 0.8,
        "matched_speed_mae_max_mps": 2,
        "travel_time_distribution_wasserstein_max_s": 2,
    }
    result = acceptance({"count_normalized_mae": 0}, limits)
    assert not result["accepted"]
    assert result["checks"]["uncapped_position_mae_m"]["missing"]
    assert not result["checks"]["signal_state_independently_verified"]["passed"]
