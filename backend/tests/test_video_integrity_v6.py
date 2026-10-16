import struct

import cv2
import numpy as np
import pytest
from atlas import db, pipeline
from atlas.api import register_video


class EmptyDetector:
    def __init__(self, _):
        pass

    def infer(self, _):
        return []


def test_truncated_avi_is_rejected_before_inference(database):
    path = database / "truncated.avi"
    path.write_bytes(b"RIFF" + struct.pack("<I", 1000000) + b"AVI " + bytes(128))
    with pytest.raises(ValueError, match="truncated"):
        pipeline.probe(path)


def test_early_decoder_end_cannot_persist_a_successful_partial_result(database, monkeypatch):
    path = database / "declared-longer.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for index in range(10):
        writer.write(np.full((48, 64, 3), index * 10, dtype=np.uint8))
    writer.release()
    identity = register_video(path, path.name, "demo")
    original = pipeline.probe

    def declared_more_frames(source):
        metadata = original(source)
        return {**metadata, "frame_count": metadata["frame_count"] + 1}

    monkeypatch.setattr(pipeline, "probe", declared_more_frames)
    with pytest.raises(ValueError, match="Incomplete video decoding"):
        pipeline.process_video(identity, EmptyDetector)
    assert db.video(identity)["status"] == "failed"
    assert not (database / "results" / f"{identity}.json").exists()
