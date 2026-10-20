from types import SimpleNamespace

import numpy as np
from atlas.live_tracker_v7 import source_overlay
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker


def test_rejects_reviewed_provider_overlays_but_keeps_actual_road_region():
    assert source_overlay([0, 0, 80, 40], (720, 1280, 3))
    assert source_overlay([1100, 0, 1200, 40], (720, 1280, 3))
    assert not source_overlay([600, 350, 650, 400], (720, 1280, 3))


def test_low_confidence_observations_recover_an_existing_identity():
    tracker = BYTETracker(
        SimpleNamespace(
            track_high_thresh=0.25,
            track_low_thresh=0.1,
            new_track_thresh=0.25,
            track_buffer=8,
            match_thresh=0.9,
            fuse_score=False,
        )
    )
    first = tracker.update(
        Boxes(np.array([[20, 20, 60, 60, 0.8, 2]], dtype=np.float32), (100, 100))
    )
    second = tracker.update(
        Boxes(np.array([[22, 20, 62, 60, 0.2, 2]], dtype=np.float32), (100, 100))
    )
    assert len(first) == len(second) == 1
    assert first[0, 4] == second[0, 4]
    # A weak unmatched detection cannot create a new vehicle identity.
    fresh = tracker.update(
        Boxes(np.array([[80, 80, 95, 95, 0.2, 2]], dtype=np.float32), (100, 100))
    )
    assert len(fresh) == 0
