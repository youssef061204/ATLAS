import numpy as np
import pytest
from atlas.multicamera_v6 import AppearanceTracklet, associate


def track(camera, identity=1, start=0, end=10, embedding=(1, 0)):
    return AppearanceTracklet(camera, identity, start, end, np.array(embedding))


def test_cross_camera_association_uses_appearance_and_published_time_offsets():
    tracks = [
        track("c006"),
        track("c007", start=11, end=20),
        track("c008", embedding=(0, 1)),
        track("c009", start=100, end=110),
    ]
    mapping, edges = associate(tracks)
    assert mapping[("c006", 1)] == mapping[("c007", 1)]
    assert mapping[("c006", 1)] != mapping[("c008", 1)]
    assert mapping[("c006", 1)] != mapping[("c009", 1)]
    assert len(edges) == 1


def test_identity_cluster_cannot_merge_two_tracklets_from_the_same_camera():
    mapping, edges = associate([track("a", 1), track("a", 2), track("b", 3)])
    assert mapping[("a", 1)] != mapping[("a", 2)]
    assert len(edges) == 1


@pytest.mark.parametrize(
    "tracks",
    [
        [track("a"), track("a")],
        [track("a", embedding=(0, 0))],
        [track("a", embedding=(1, float("nan")))],
        [track("a", start=20, end=10)],
        [track("a"), track("b", embedding=(1, 0, 0))],
    ],
)
def test_invalid_identity_features_fail_closed(tracks):
    with pytest.raises(ValueError):
        associate(tracks)
