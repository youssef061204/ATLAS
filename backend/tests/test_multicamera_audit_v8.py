import numpy as np
from atlas.multicamera_audit_v8 import audit_annotation_evidence


def test_annotation_audit_keeps_unlabeled_predictions_and_checks_link_identity():
    roi = np.full((100, 100), 255, dtype=np.uint8)
    metadata = {camera: {"fps": 10, "frame_count": 4} for camera in ("a", "b")}
    tracks = [
        {
            "camera": camera,
            "id": identity,
            "points": [{"t": frame / 10, "bbox": box} for frame in range(3)],
        }
        for camera, identity, box in (
            ("a", 1, [10, 10, 30, 30]),
            ("a", 2, [60, 60, 80, 80]),
            ("b", 1, [10, 10, 30, 30]),
        )
    ]
    annotations = {
        camera: np.asarray([[frame, 42, 10, 10, 20, 20] for frame in range(1, 4)])
        for camera in ("a", "b")
    }
    links = [
        {"left": ["a", 1], "right": ["b", 1]},
        {"left": ["a", 2], "right": ["b", 1]},
    ]
    result = audit_annotation_evidence(
        tracks, {"a": roi, "b": roi}, metadata, annotations, links, padding=0
    )
    totals = result["totals"]
    assert totals["annotated_boxes"] == 6
    assert totals["predicted_boxes"] == 9
    assert totals["matched_annotated_boxes"] == 6
    assert totals["predicted_boxes_in_unannotated_frames"] == 0
    assert totals["prediction_annotation_match_fraction"] == 6 / 9
    assert totals["annotated_multicamera_vehicles"] == 1
    assert result["accepted_link_audit"]["cross_camera"] == {
        "same_annotated_vehicle": 1,
        "different_annotated_vehicles": 0,
        "not_checkable_from_labels": 1,
    }
    assert totals["annotated_vehicles_with_verified_cross_camera_links"] == 1


def test_annotation_audit_exposes_wrong_link_and_unlabeled_frame():
    roi = np.full((100, 100), 255, dtype=np.uint8)
    tracks = [
        {
            "camera": camera,
            "id": 1,
            "points": [{"t": frame / 10, "bbox": [10, 10, 30, 30]} for frame in range(3)],
        }
        for camera in ("a", "b")
    ]
    tracks.append({"camera": "a", "id": 2, "points": [{"t": 0.3, "bbox": [60, 60, 80, 80]}]})
    annotations = {
        camera: np.asarray([[frame, identity, 10, 10, 20, 20] for frame in range(1, 4)])
        for camera, identity in (("a", 42), ("b", 99))
    }
    result = audit_annotation_evidence(
        tracks,
        {"a": roi, "b": roi},
        {camera: {"fps": 10, "frame_count": 4} for camera in ("a", "b")},
        annotations,
        [{"left": ["a", 1], "right": ["b", 1]}],
        padding=0,
    )
    assert result["totals"]["predicted_boxes_in_unannotated_frames"] == 1
    assert result["accepted_link_audit"]["cross_camera"]["different_annotated_vehicles"] == 1
    assert set(result) == {"totals", "per_camera", "accepted_link_audit", "accepted_link_kinds"}
