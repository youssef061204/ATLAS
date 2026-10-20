import numpy as np
import pytest
from atlas.multicamera_metrics_v7 import evaluate, overlap, padded_box
from atlas.multicamera_reid_v7 import associate, handoff_evidence
from atlas.multicamera_v7 import GeoTracklet, associate_geometry


def test_evaluation_uses_actual_eight_fps_source_and_keeps_padding_cohort():
    roi = np.full((100, 100), 255, dtype=np.uint8)
    tracks = [{"camera": "slow", "id": 7, "points": [{"t": 0.5, "bbox": [20, 20, 40, 40]}]}]
    annotations = {"slow": np.array([[5, 42, 10, 10, 40, 40]])}
    args = (
        tracks,
        {("slow", 7): 1},
        {"slow": roi},
        {"slow": {"fps": 8, "frame_count": 8}},
        annotations,
    )
    raw = evaluate(*args)
    aligned = evaluate(*args, padding=10)
    assert raw["predicted_boxes"] == aligned["predicted_boxes"] == 1
    assert raw["identity"]["IDF1"] == 0
    assert aligned["identity"]["IDF1"] == 1


def test_padding_does_not_shift_the_box_center_or_claim_physical_dimensions():
    assert padded_box([10, 20, 30, 40], 10).tolist() == [0, 10, 40, 50]
    assert overlap([], [[0, 0, 1, 1]]).shape == (0, 1)
    with pytest.raises(ValueError):
        padded_box([0, 0, 1, 1], -1)


def test_geometric_association_rejects_ambiguous_same_camera_rivals():
    t = np.arange(0, 2, 0.1)
    xy = np.column_stack([t * 5, np.zeros(len(t))])
    tracks = [
        GeoTracklet("a", 1, t, xy),
        GeoTracklet("b", 2, t, xy + [0.1, 0]),
        GeoTracklet("b", 3, t, xy + [0.2, 0]),
    ]
    mapping, accepted, diagnostic = associate_geometry(tracks)
    assert accepted == []
    assert diagnostic["ambiguous_rejections"] == 2
    assert len(set(mapping.values())) == 3


def test_a_true_three_camera_observation_is_not_mistaken_for_a_rival():
    t = np.arange(0, 2, 0.1)
    xy = np.column_stack([t * 5, np.zeros(len(t))])
    mapping, accepted, _ = associate_geometry(
        [GeoTracklet(camera, 1, t, xy) for camera in ["a", "b", "c"]]
    )
    assert len(set(mapping.values())) == 1
    assert len(accepted) == 2


def test_color_handoff_also_requires_consistent_physical_motion():
    a_t, b_t = np.arange(0, 2, 0.1), np.arange(3, 5, 0.1)
    a = GeoTracklet("a", 1, a_t, np.column_stack([a_t * 5, a_t * 0]))
    b = GeoTracklet("b", 2, b_t, np.column_stack([b_t * 5, b_t * 0]))
    assert handoff_evidence(a, b, 0.95)["kind"] == "time_geometry_appearance_handoff"
    assert handoff_evidence(a, b, 0.4) is None
    reversed_track = GeoTracklet("b", 2, b_t, b.xy_m[::-1])
    assert handoff_evidence(a, reversed_track, 1) is None
    static = GeoTracklet("b", 2, b_t, np.zeros_like(b.xy_m))
    assert handoff_evidence(a, static, 1) is None


def test_group_can_bridge_disjoint_fragments_without_merging_simultaneous_ids():
    a_t, b_t = np.arange(0, 1, 0.1), np.arange(1.1, 2, 0.1)
    a = GeoTracklet("a", 1, a_t, np.column_stack([a_t * 5, a_t * 0]))
    b = GeoTracklet("a", 2, b_t, np.column_stack([b_t * 5, b_t * 0]))
    mapping, links, _ = associate(
        [a, b], {("a", 1): np.array([1.0, 0]), ("a", 2): np.array([1.0, 0])}
    )
    assert len(set(mapping.values())) == 1
    assert links[0]["kind"] == "same_camera_fragment"
    # Same-camera simultaneous detections can never be a valid continuation.
    assert handoff_evidence(a, GeoTracklet("a", 3, a_t, a.xy_m.copy()), 1) is None
