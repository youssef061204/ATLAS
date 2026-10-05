"""Verify actual upload, inference, camera reprocessing, SSE, replay, and metrics over HTTP."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from atlas import config
from atlas.experiments import save


def wait_for_job(client, video_id):
    statuses, ages = [], []
    deadline = time.monotonic() + 240
    with client.stream("GET", f"/api/videos/{video_id}/events-stream") as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                raise TimeoutError("Inference did not finish within four minutes")
            if not line.startswith("data: "):
                continue
            value = json.loads(line[6:])
            statuses.append({"stage": value["stage"], "progress": value["progress"]})
            if value.get("updated_at") and value["status"] == "processing":
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(value["updated_at"])
                ).total_seconds()
                if age >= 0:
                    ages.append(age * 1000)
            if value["status"] == "failed":
                raise RuntimeError(value["error"])
            if value["status"] == "complete":
                return {
                    "status_events": statuses,
                    "status_delivery_ms": {
                        f"p{q}": float(np.percentile(ages, q)) for q in [50, 95, 99]
                    }
                    if ages
                    else None,
                }
    raise RuntimeError("SSE closed without a terminal status")


def main(args):
    with httpx.Client(base_url=args.url, timeout=240) as client:
        client.get("/health").raise_for_status()
        with args.video.open("rb") as source:
            response = client.post("/api/videos", files={"file": ("demo.mp4", source, "video/mp4")})
        response.raise_for_status()
        video_id = response.json()["id"]
        print(f"Actual upload accepted: {video_id}", flush=True)
        upload = wait_for_job(client, video_id)
        print("Initial inference finished; reprocessing with the aerial camera profile", flush=True)
        settings = json.loads((config.ROOT / "docs/demo-camera.json").read_text())
        client.put(f"/api/videos/{video_id}/camera", json=settings).raise_for_status()
        client.post(f"/api/videos/{video_id}/reprocess").raise_for_status()
        aerial = wait_for_job(client, video_id)
        result = client.get(f"/api/videos/{video_id}/result").json()
        assert result["performance"]["processed_frames"] == 480
        assert len(result["frames"]) == 480
        assert {"car", "person"}.issubset(result["summary"]["classes"])
        tracks = client.get(f"/api/videos/{video_id}/tracks").json()
        metrics = client.get(f"/api/videos/{video_id}/metrics").json()
        assert len(tracks) == result["summary"]["unique_tracks"]
        assert len(metrics) == 480 and metrics[-1]["speed_unit"] == "px/s"
        assert client.get(f"/api/videos/{video_id}/safety").json() == []
        assert (
            client.get(f"/api/videos/{video_id}/forecast").json()["status"]
            == "insufficient_history"
        )
        source = client.get(f"/api/videos/{video_id}/source", headers={"Range": "bytes=0-63"})
        assert source.status_code == 206 and len(source.content) == 64
        prometheus = client.get("/metrics").text
        assert f'atlas_processed_frames{{video="{video_id}"}} 480.0' in prometheus
        artifact = save(
            "live-verification",
            {
                "scope": "Actual HTTP upload and fresh CPU inference/reprocessing through the running application; integration verification, not detection accuracy. Stage delivery age is not frame-to-screen latency.",
                "url": args.url,
                "video_id": video_id,
                "upload": upload,
                "aerial_reprocess": aerial,
                "performance": result["performance"],
                "checks": {
                    "upload": True,
                    "sse": True,
                    "camera_reprocessing": True,
                    "relational_tracks_metrics": True,
                    "range_replay": True,
                    "calibration_gate": True,
                    "history_gate": True,
                    "prometheus_worker_metrics": True,
                },
            },
        )
        print(json.dumps(artifact["performance"], indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--video", type=Path, default=config.DATA / "demo.mp4")
    main(parser.parse_args())
