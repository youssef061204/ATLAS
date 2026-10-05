import cv2
import numpy as np
import pytest
from atlas import db
from atlas.api import app, register_video
from atlas.pipeline import probe, process_video
from fastapi.testclient import TestClient


def tiny_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for _ in range(10):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()


class EmptyDetector:
    def __init__(self, settings):
        pass

    def infer(self, frame):
        return []


def test_pipeline_persists_empty_detections_without_fake_metrics(database):
    path = database / "sample.avi"
    tiny_video(path)
    video_id = register_video(path, "sample.avi", "demo")
    result = process_video(video_id, EmptyDetector)
    assert result["summary"]["unique_tracks"] == 0
    assert all(m["vehicles"] == 0 for m in result["metrics"])
    assert db.video(video_id)["status"] == "complete"
    assert (database / "results" / f"{video_id}.json").exists()
    with TestClient(app) as client:
        response = client.get("/metrics").text
        assert "atlas_processed_frames" in response
        assert f'video="{video_id}"' in response


def test_corrupt_input_and_missing_model_error_are_persisted(database):
    path = database / "broken.mp4"
    path.write_bytes(b"not a video")
    with pytest.raises(ValueError):
        probe(path)
    path = database / "sample.avi"
    tiny_video(path)
    video_id = register_video(path, "sample.avi", "demo")

    def missing_model(settings):
        raise FileNotFoundError("Missing detector model")

    with pytest.raises(FileNotFoundError):
        process_video(video_id, missing_model)
    assert db.video(video_id)["status"] == "failed"
    assert "Missing" in db.video(video_id)["error"]


def test_api_validates_input_and_supports_persisted_results(database):
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/videos/unknown").status_code == 404
        assert client.post("/api/videos", files={"file": ("bad.exe", b"abc")}).status_code == 415
        assert client.post("/api/videos", files={"file": ("empty.mp4", b"")}).status_code == 422
        assert client.post("/api/intersections", json={"name": ""}).status_code == 422
        assert client.post("/api/simulations", json={"demand": [1, -1, 0, 0]}).status_code == 422
        assert (
            client.post(
                "/api/streams", json={"url": "http://localhost/video", "intersection_id": "demo"}
            ).status_code
            == 403
        )
        value = client.post("/api/intersections", json={"name": "Test site"}).json()
        assert value["name"] == "Test site"
        assert client.get("/metrics").status_code == 200


def test_database_failure_health_is_service_unavailable(database, monkeypatch):
    with TestClient(app) as client:

        def unavailable(*args):
            raise RuntimeError("Unavailable")

        monkeypatch.setattr(db, "rows", unavailable)
        assert client.get("/health").status_code == 503
