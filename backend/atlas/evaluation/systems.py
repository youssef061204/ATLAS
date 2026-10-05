"""Full production pipeline benchmark on lossless encodings of real annotated frames."""

import gc
import json
import threading
import time

import cv2
import numpy as np
import psutil

from atlas import config, db
from atlas.detector import YOLOTracker
from atlas.evaluation.artifacts import write_artifact
from atlas.evaluation.data import DATASETS, validated_detrac_frames
from atlas.schemas import CameraConfig


def evaluate_real_video():
    from atlas.api import register_video
    from atlas.pipeline import process_video

    root = DATASETS / "ua-detrac"
    manifest = json.loads((root / "manifest.json").read_text())
    previous_data = config.DATA
    config.DATA = DATASETS / "evaluation-runs" / "pipeline-runtime"
    for directory in [config.DATA, config.DATA / "uploads", config.DATA / "results"]:
        directory.mkdir(parents=True, exist_ok=True)
    db.init()
    output, all_latency = [], []
    try:
        for sequence in manifest["splits"]["test"]:
            name = sequence["sequence"]
            folder = root / "test" / name
            frames = validated_detrac_frames(root, "test", name, manifest)
            clip = config.DATA / f"{name}.avi"
            writer = cv2.VideoWriter(
                str(clip),
                cv2.VideoWriter_fourcc(*"FFV1"),
                manifest["fps"],
                (frames[0]["width"], frames[0]["height"]),
            )
            if not writer.isOpened():
                raise RuntimeError("OpenCV FFV1 lossless encoder is unavailable")
            for frame in frames:
                image = cv2.imread(str(folder / frame["filename"]))
                writer.write(image)
            writer.release()
            # Verify decoding reproduces the original first frame pixel-for-pixel.
            capture = cv2.VideoCapture(str(clip))
            ok, decoded = capture.read()
            capture.release()
            if not ok or not np.array_equal(
                decoded, cv2.imread(str(folder / frames[0]["filename"]))
            ):
                raise ValueError("Lossless evaluation video did not preserve source pixels")
            identity = register_video(clip, name + ".avi", "demo")
            settings = CameraConfig(sample_every=1)
            with db.connection() as conn:
                conn.execute(
                    "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
                    (settings.model_dump_json(), identity),
                )
            process = psutil.Process()
            memory, done = [], threading.Event()

            def sample_memory(completion=done, samples=memory, measured_process=process):
                while not completion.wait(0.1):
                    samples.append(measured_process.memory_info().rss)

            monitor = threading.Thread(target=sample_memory, daemon=True)
            cpu_start = sum(process.cpu_times()[:2])
            before = time.perf_counter()
            monitor.start()
            try:
                result = process_video(identity, YOLOTracker)
            finally:
                done.set()
                monitor.join()
            elapsed = time.perf_counter() - before
            cpu_seconds = sum(process.cpu_times()[:2]) - cpu_start
            latency = [f["inference_ms"] for f in result["frames"]]
            all_latency.extend(latency)
            output.append(
                {
                    "sequence": name,
                    "frames": len(result["frames"]),
                    "source_duration_seconds": len(frames) / manifest["fps"],
                    "total_pipeline_wall_seconds": elapsed,
                    "pipeline_fps": len(frames) / elapsed,
                    "detector_tracker_fps": len(frames) / (sum(latency) / 1000),
                    "inference_ms": {
                        f"p{q}": float(np.percentile(latency, q)) for q in [50, 95, 99]
                    },
                    "memory_peak_rss_mb": max(memory or [process.memory_info().rss]) / 1024**2,
                    "cpu_process_percent": cpu_seconds / elapsed * 100,
                    "cpu_machine_capacity_percent": cpu_seconds
                    / elapsed
                    / psutil.cpu_count()
                    * 100,
                    "cpu_seconds": cpu_seconds,
                    "safety_events": len(result["events"]),
                    "safety_status": "disabled: no verified metric calibration",
                    "pipeline_performance": result["performance"],
                }
            )
            print(
                f"Real-video pipeline {name}: {len(frames)} frames, {len(frames) / elapsed:.2f} FPS",
                flush=True,
            )
            del result
            gc.collect()
    finally:
        config.DATA = previous_data
    frames = sum(r["frames"] for r in output)
    wall = sum(r["total_pipeline_wall_seconds"] for r in output)
    write_artifact(
        "real_safety_qualitative",
        benchmark_type="safety_qualitative",
        data_provenance="real",
        dataset="UA-DETRAC",
        dataset_version=manifest["revision"],
        model="Production calibration-gated SafetyEngine",
        split={"sequences": [r["sequence"] for r in output], "frames": frames},
        metrics={
            "frames": frames,
            "generated_events": sum(r["safety_events"] for r in output),
            "supervised_auroc": None,
            "supervised_f1": None,
            "ttc_distribution": None,
            "pet_distribution": None,
            "minimum_separation_distribution": None,
        },
        scope="Real-world qualitative / trajectory-based validation is limited to verifying the calibration gate on real footage. No real conflict accuracy or physical trajectory validation is claimed.",
        methodology={
            "gate": "No verified surveyed metric calibration; safety engine invoked and correctly disabled",
            "source_artifact": "real_video_pipeline.json",
        },
        results={"status": "gated: metric calibration unavailable", "replay_events": []},
    )
    return write_artifact(
        "real_video_pipeline",
        benchmark_type="systems",
        data_provenance="real",
        dataset="UA-DETRAC",
        dataset_version=manifest["revision"],
        model=f"{config.MODEL} + ByteTrack + production analytics/persistence",
        seed=None,
        split={
            "sequences": [r["sequence"] for r in output],
            "frames": frames,
            "partition": "official test",
        },
        metrics={
            "pipeline_fps": frames / wall,
            "frames": frames,
            "total_pipeline_wall_seconds": wall,
            "inference_ms": {f"p{q}": float(np.percentile(all_latency, q)) for q in [50, 95, 99]},
            "seconds_per_minute_video": wall / (frames / manifest["fps"]) * 60,
            "memory_peak_rss_mb": max(r["memory_peak_rss_mb"] for r in output),
            "cpu_process_percent": sum(r["cpu_seconds"] for r in output) / wall * 100,
            "cpu_machine_capacity_percent": sum(r["cpu_seconds"] for r in output)
            / wall
            / psutil.cpu_count()
            * 100,
            "events_per_second": sum(r["safety_events"] for r in output) / wall,
        },
        scope="Actual annotated traffic frames encoded losslessly at the published 25 FPS. Fresh complete production pipeline runs; includes initialization, analytics, SQLite and JSON persistence. CPU only.",
        methodology={
            "settings": settings.model_dump(),
            "preprocessing": "FFV1 encoding performed before timing; first decoded frame verified pixel-identical",
            "latency": "Detector+tracker time per frame; separate detector-only throughput is in real_video_systems",
            "events": "Safety engine invoked but gated off by absent calibration. Zero generated events is not validated risk detection throughput.",
            "memory": "Peak process RSS sampled every 0.1 s; sequential runs in one process retain allocator caches",
            "cpu": "Process CPU-seconds/wall-time can exceed 100%; machine-capacity percentage divides by logical cores",
            "load": "Developer machine; not a dedicated isolated performance host",
        },
        results={"sequences": output},
    )
