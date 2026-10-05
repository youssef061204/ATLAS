import json
import logging
import time
from pathlib import Path

import cv2
import joblib
import numpy as np
import psutil

from . import config, db
from .analytics import TrajectoryEngine
from .detector import YOLOTracker
from .forecast import forecast_from_metrics
from .geometry import Projection
from .safety import SafetyEngine
from .schemas import CameraConfig

log = logging.getLogger("atlas.pipeline")


def probe(path: Path):
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("Unsupported or corrupt video container")
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, _ = capture.read()
        if not ok or not np.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError("Video has no decodable frames or valid timestamps")
        duration = count / fps
        if duration > config.MAX_SECONDS:
            raise ValueError(f"Video exceeds {config.MAX_SECONDS:.0f} s limit")
        return {
            "fps": fps,
            "frame_count": count,
            "duration": duration,
            "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
    finally:
        capture.release()


def persist(video_id, result):
    # Replace atomically at the relational level; IDs are scoped to one run/video.
    with db.connection() as conn:
        for table in [
            "trajectory_points",
            "tracks",
            "frames",
            "traffic_metrics",
            "safety_events",
            "forecasts",
        ]:
            conn.execute(f"DELETE FROM {table} WHERE video_id=?", (video_id,))
        for track in result["tracks"]:
            points = track["points"]
            summary = {k: v for k, v in track.items() if k != "points"}
            conn.execute(
                "INSERT INTO tracks VALUES (?,?,?,?,?,?)",
                (
                    video_id,
                    track["id"],
                    track["class"],
                    points[0]["t"],
                    points[-1]["t"],
                    json.dumps(summary),
                ),
            )
            conn.executemany(
                "INSERT INTO trajectory_points VALUES (?,?,?,?)",
                [(video_id, track["id"], p["t"], json.dumps(p)) for p in points],
            )
        conn.executemany(
            "INSERT INTO frames VALUES (?,?,?,?,?)",
            [
                (video_id, f["index"], f["t"], f["inference_ms"], len(f["objects"]))
                for f in result["frames"]
            ],
        )
        conn.executemany(
            "INSERT INTO traffic_metrics VALUES (?,?,?)",
            [(video_id, m["t"], json.dumps(m)) for m in result["metrics"]],
        )
        conn.executemany(
            "INSERT INTO safety_events VALUES (?,?,?,?,?)",
            [(e["id"], video_id, e["t"], e["severity"], json.dumps(e)) for e in result["events"]],
        )
        conn.execute(
            "INSERT INTO forecasts VALUES (?,?,?)",
            (db.uid(), video_id, json.dumps(result["forecast"])),
        )
    target = config.DATA / "results" / f"{video_id}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(result, allow_nan=False, separators=(",", ":")), encoding="utf-8"
    )
    temporary.replace(target)


def process_video(video_id, detector_factory=YOLOTracker):
    start = time.perf_counter()
    capture = None
    try:
        row = db.rows(
            "SELECT v.*,c.config FROM videos v JOIN cameras c ON v.camera_id=c.id WHERE v.id=?",
            (video_id,),
        )[0]
        db.status(video_id, "processing", "preprocessing", 0.01)
        metadata = probe(Path(row["storage_path"]))
        settings = CameraConfig.model_validate_json(row["config"])
        projection = Projection(settings.calibration)
        engine = TrajectoryEngine(projection, settings.regions)
        risk_model_path = config.ARTIFACTS / "models" / "risk.joblib"
        safety = SafetyEngine(
            projection.verified, joblib.load(risk_model_path) if risk_model_path.exists() else None
        )
        detector = detector_factory(settings)
        capture = cv2.VideoCapture(row["storage_path"])
        frames, latencies = [], []
        index = 0
        first_frame_latency = None
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % settings.sample_every == 0:
                infer_start = time.perf_counter()
                detections = detector.infer(frame)
                latency = time.perf_counter() - infer_start
                t = index / metadata["fps"]
                objects, _ = engine.update(t, detections)
                safety.update(t, objects)
                frames.append(
                    {
                        "index": index,
                        "t": round(t, 4),
                        "inference_ms": round(latency * 1000, 3),
                        "objects": objects,
                    }
                )
                latencies.append(latency * 1000)
                if first_frame_latency is None:
                    first_frame_latency = time.perf_counter() - start
                if len(frames) % 10 == 0:
                    db.status(
                        video_id,
                        "processing",
                        "detection_tracking",
                        min(0.9, index / metadata["frame_count"] * 0.9),
                        metadata={
                            **metadata,
                            "live_metric": engine.metrics[-1],
                            "live_performance": {
                                "processed_frames": len(frames),
                                "inference_ms": {
                                    f"p{q}": float(np.percentile(latencies, q))
                                    for q in [50, 95, 99]
                                },
                            },
                        },
                    )
            index += 1
        if not frames:
            raise ValueError("No sampled frames decoded")
        db.status(video_id, "processing", "analytics_safety", 0.94)
        forecasting = forecast_from_metrics(engine.metrics)
        elapsed = time.perf_counter() - start
        summary = engine.summary()
        perf = {
            "device": config.DEVICE,
            "model": getattr(detector, "model_identifier", config.MODEL),
            "tracker": settings.tracker,
            "resolution": settings.resolution,
            "sample_every": settings.sample_every,
            "processed_frames": len(frames),
            "decoded_frames": index,
            "wall_seconds": round(elapsed, 3),
            "processed_fps": round(len(frames) / elapsed, 3),
            "video_seconds_per_wall_second": round(metadata["duration"] / elapsed, 3),
            "inference_ms": {
                f"p{q}": round(float(np.percentile(latencies, q)), 3) for q in [50, 95, 99]
            },
            "memory_rss_mb": round(psutil.Process().memory_info().rss / 1024**2, 2),
            "first_result_seconds": round(first_frame_latency, 3),
            "source_size_bytes": Path(row["storage_path"]).stat().st_size,
        }
        result = {
            "video_id": video_id,
            "metadata": metadata,
            "config": settings.model_dump(),
            "summary": summary,
            "frames": frames,
            "tracks": list(engine.tracks.values()),
            "metrics": engine.metrics,
            "events": safety.events,
            "forecast": forecasting,
            "performance": perf,
            "provenance": {
                "generated_at": db.now(),
                "source": row["filename"],
                "pipeline": "YOLO + persistent ByteTrack/BoT-SORT → timestamp regression → analytics",
                "safety": "verified calibration required",
                "accuracy_evaluation": "Not measured on this unlabeled footage",
                "sample_scope": "Overhead time-lapse; timestamps are playback seconds, not field elapsed time"
                if row["filename"] == "demo.mp4"
                else "User-supplied footage; timestamps follow the source frame rate",
            },
            "scene": {
                "homography": projection.matrix.tolist() if projection.matrix is not None else None
            },
        }
        persist(video_id, result)
        perf["result_size_bytes"] = (config.DATA / "results" / f"{video_id}.json").stat().st_size
        db.status(
            video_id,
            "complete",
            "complete",
            1,
            metadata={**metadata, "summary": summary, "performance": perf},
        )
        db.save_run("pipeline", perf, row["intersection_id"])
        log.info(
            "video_complete",
            extra={"video_id": video_id, "frames": len(frames), "seconds": elapsed},
        )
        return result
    except Exception as exc:
        db.status(video_id, "failed", "failed", 0, error=str(exc)[:500])
        log.exception("video_failed", extra={"video_id": video_id})
        raise
    finally:
        if capture is not None:
            capture.release()
