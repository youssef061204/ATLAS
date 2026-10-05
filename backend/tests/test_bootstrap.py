import gzip
import hashlib
import json

import pytest
from atlas import config, db
from atlas.cli import load_demo_cache


def test_cache_verifies_both_source_and_result_integrity(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARTIFACTS", tmp_path)
    demo = tmp_path / "demo"
    demo.mkdir()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source fixture")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = demo / "result.json.gz"
    with gzip.open(cache, "wt", encoding="utf-8") as output:
        json.dump({"provenance": {"source_sha256": source_sha}}, output)
    cache_sha = hashlib.sha256(cache.read_bytes()).hexdigest()
    (demo / "manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": source_sha,
                "artifact_sha256": cache_sha,
            }
        )
    )
    assert load_demo_cache(source)[1] == cache_sha
    source.write_bytes(b"different footage")
    with pytest.raises(ValueError, match="differs from the cached source"):
        load_demo_cache(source)
    cache.write_bytes(b"tampered cache")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_demo_cache(source)


def test_cli_initialization_does_not_interrupt_jobs(database):
    from atlas.api import register_video
    from test_pipeline_api import tiny_video

    path = database / "source.avi"
    tiny_video(path)
    video_id = register_video(path, "source.avi", "demo")
    db.init()
    assert db.video(video_id)["status"] == "queued"
    db.init(recover=True)
    assert db.video(video_id)["status"] == "failed"
