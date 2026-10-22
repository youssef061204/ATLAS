from atlas.lifecycle_v8 import audit_lifecycle, spatial_cv_matches


def test_spatial_cv_matching_is_one_to_one_and_gated():
    reference = [
        {"id": "a", "point": [0, 0]},
        {"id": "b", "point": [3, 0]},
        {"id": "c", "point": [20, 0]},
    ]
    cv = [
        {"id": "1", "point": [0.1, 0]},
        {"id": "2", "point": [3.2, 0]},
        {"id": "3", "point": [30, 0]},
    ]
    assert spatial_cv_matches(reference, cv) == {"a": "1", "b": "2"}


def test_lifecycle_stages_partition_reference_states_without_dropping_misses():
    reference = {
        0: [
            {"id": "unmatched", "point": [0, 0]},
            {"id": "late_cv", "point": [10, 0]},
            {"id": "never", "point": [20, 0]},
            {"id": "late_native", "point": [30, 0]},
            {"id": "exited", "point": [40, 0]},
            {"id": "gap", "point": [50, 0]},
            {"id": "far", "point": [60, 0]},
            {"id": "near", "point": [70, 0]},
        ]
    }
    mapping = {
        identity: {
            "native_id": f"cv_{identity}",
            "birth_s": 1 if identity == "late_cv" else 0,
            "birth_association_distance_m": 0,
        }
        for identity in ["late_cv", "never", "late_native", "exited", "gap", "far", "near"]
    }
    entries = [{"id": f"cv_{identity}", "edge": "S_in", "lane": 1} for identity in mapping]
    native = {
        0: [
            {"id": "cv_exited", "point": [40, 0]},
            {"id": "cv_far", "point": [70, 0]},
            {"id": "cv_near", "point": [71, 0]},
        ],
        1: [
            {"id": "cv_late_native", "point": [30, 0]},
            {"id": "cv_gap", "point": [50, 0]},
        ],
        2: [{"id": "cv_gap", "point": [50, 0]}],
    }
    # The classifier uses a full native output timeline even when scoring t=0.
    result = audit_lifecycle(
        reference,
        {0: [{"id": "cv_unmatched", "point": [0, 0]}]},
        entries,
        mapping,
        native,
        0,
        1,
    )
    assert result["reference_states"] == 8
    assert sum(result["stage_counts"].values()) == 8
    assert result["stage_counts"] == {
        "before_cv_birth": 1,
        "before_first_native_sample": 2,
        "native_beyond_4m": 1,
        "native_within_4m": 2,
        "no_birth_association": 1,
        "requested_never_sampled_native": 1,
    }
    assert result["same_second_cv_matched_reference_states"] == 1
    assert result["same_second_cv_match_by_stage"]["no_birth_association"]["matched"] == 1
    assert result["same_second_cv_identity_by_stage"]["no_birth_association"]["other_cv_id"] == 1


def test_after_last_native_sample_and_sample_gap_are_distinct():
    reference = {
        10: [
            {"id": "exited", "point": [0, 0]},
            {"id": "gap", "point": [10, 0]},
        ]
    }
    mapping = {
        identity: {"native_id": identity, "birth_s": 0, "birth_association_distance_m": 0}
        for identity in ["exited", "gap"]
    }
    native = {
        0: [{"id": "exited", "point": [0, 0]}, {"id": "gap", "point": [10, 0]}],
        2: [{"id": "gap", "point": [10, 0]}],
    }
    result = audit_lifecycle(reference, {}, [], mapping, native, 1, 2)
    assert result["stage_counts"] == {"after_last_native_sample": 1, "native_sample_gap": 1}
    assert result["native_presence_coverage"] == 0
