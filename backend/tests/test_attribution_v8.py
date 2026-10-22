from atlas.attribution_v8 import admission_lifecycle, state_attribution


def test_every_reference_state_stays_in_one_exclusive_error_bucket():
    reference = {
        10: [
            {"id": "missing", "point": [0, 0]},
            {"id": "late", "point": [0, 0]},
            {"id": "absent", "point": [0, 0]},
            {"id": "far", "point": [0, 0]},
            {"id": "near", "point": [0, 0]},
        ]
    }
    mapping = {
        "late": {"native_id": "v_late", "birth_s": 2},
        "absent": {"native_id": "v_absent", "birth_s": 0},
        "far": {"native_id": "v_far", "birth_s": 0},
        "near": {"native_id": "v_near", "birth_s": 0},
    }
    native = {1: [{"id": "v_far", "point": [5, 0]}, {"id": "v_near", "point": [4, 0]}]}
    report = state_attribution(mapping, reference, native, 1, 2)
    assert report["reference_states"] == 5
    assert {key: row["states"] for key, row in report["exclusive_state_categories"].items()} == {
        "no_cv_birth_association": 1,
        "before_cv_birth": 1,
        "native_vehicle_absent": 1,
        "native_present_outside_gate": 1,
        "native_present_within_gate": 1,
    }


def test_native_sample_lifecycle_does_not_call_requested_departure_actual():
    entries = [
        {"id": "cv_a", "t": 0.4, "edge": "S_in", "lane": 1},
        {"id": "cv_b", "t": 0.5, "edge": "N_in", "lane": 0},
    ]
    native = {1: [{"id": "cv_a", "point": [0, 0]}], 2: [{"id": "cv_a", "point": [1, 0]}]}
    report = admission_lifecycle(entries, {"ref_7": {"native_id": "cv_a"}}, native, 3)
    assert report["requested_births"] == 2
    assert report["sampled_native_births"] == 1
    assert report["unsampled_native_births"] == 1
    assert report["records"][0]["first_sample_offset_s"] == 0.6
    assert report["records"][1]["first_sampled_native_s"] is None
    assert report["records"][0]["reference_id"] == "ref_7"
