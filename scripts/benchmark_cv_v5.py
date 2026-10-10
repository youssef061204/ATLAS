"""Repeated fresh complete production runs, with separate accuracy scoring."""

import gc
import hashlib
import json
import platform
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import psutil
import torch
import trackeval
from atlas import config, db
from atlas.api import register_video
from atlas.detector import YOLOTracker
from atlas.evaluation.data import validated_detrac_frames
from atlas.evaluation.vision import VEHICLES, ignore_predictions, tracking_input
from atlas.pipeline import process_video
from atlas.schemas import CameraConfig


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def accuracy(frames, result):
    tracks = [
        ignore_predictions(
            f["objects"], [o for o in observed["objects"] if o["class"] in VEHICLES], f["ignored"]
        )
        for f, observed in zip(frames, result["frames"], strict=True)
    ]
    value = tracking_input(frames, tracks)
    identity = trackeval.metrics.Identity().eval_sequence(value)
    hota = trackeval.metrics.HOTA().eval_sequence(value)
    clear = trackeval.metrics.CLEAR().eval_sequence(value)
    return {
        "idf1": float(identity["IDF1"]),
        "hota": float(np.mean(hota["HOTA"])),
        "identity_switches": int(clear["IDSW"]),
        "visible_vehicle_count_mae": float(
            np.mean([abs(len(f["objects"]) - len(t)) for f, t in zip(frames, tracks, strict=True)])
        ),
    }


def main():
    protocol_path = Path("docs/cv-v5-protocol.json")
    protocol = json.loads(protocol_path.read_text())
    root = Path("datasets/ua-detrac")
    manifest = json.loads((root / "manifest.json").read_text())
    sequence = protocol["sequence"]
    frames = validated_detrac_frames(root, "test", sequence, manifest)
    assert len(frames) == protocol["frames_per_run"]
    config.DATA = Path("data/cv-v5/full-pipeline").resolve()
    config.DEVICE, config.MODEL = "cpu", protocol["model"]
    for path in (config.DATA, config.DATA / "uploads", config.DATA / "results"):
        path.mkdir(parents=True, exist_ok=True)
    db.init()
    clip = config.DATA / f"{sequence}.avi"
    writer = cv2.VideoWriter(
        str(clip),
        cv2.VideoWriter_fourcc(*"FFV1"),
        manifest["fps"],
        (frames[0]["width"], frames[0]["height"]),
    )
    if not writer.isOpened():
        raise ValueError("Lossless encoder unavailable")
    for frame in frames:
        writer.write(cv2.imread(str(root / "test" / sequence / frame["filename"])))
    writer.release()
    capture = cv2.VideoCapture(str(clip))
    ok, decoded = capture.read()
    capture.release()
    if not ok or not np.array_equal(
        decoded, cv2.imread(str(root / "test" / sequence / frames[0]["filename"]))
    ):
        raise ValueError("Encoded evaluation pixels differ")
    runs = []
    for repetition, trackers in enumerate(protocol["order"], 1):
        for tracker in trackers:
            settings = CameraConfig(
                sample_every=1,
                tracker=tracker,
                resolution=protocol["resolution"],
                confidence=protocol["confidence"],
            )
            identity = register_video(clip, sequence + ".avi", "demo")
            with db.connection() as conn:
                conn.execute(
                    "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
                    (settings.model_dump_json(), identity),
                )
            gc.collect()
            torch.set_num_threads(4)
            cv2.setNumThreads(1)
            process = psutil.Process()
            memory, done = [], threading.Event()

            def monitor(completion=done, samples=memory, measured_process=process):
                while not completion.wait(0.1):
                    samples.append(measured_process.memory_info().rss)

            thread = threading.Thread(target=monitor, daemon=True)
            machine_load = psutil.cpu_percent(interval=0.25)
            cpu_before = sum(process.cpu_times()[:2])
            started = time.perf_counter()
            thread.start()
            try:
                result = process_video(identity, YOLOTracker)
            finally:
                done.set()
                thread.join()
            elapsed = time.perf_counter() - started
            cpu = sum(process.cpu_times()[:2]) - cpu_before
            assert len(result["frames"]) == len(frames)
            runs.append(
                {
                    "repetition": repetition,
                    "tracker": tracker,
                    "frames": len(frames),
                    "complete_pipeline_wall_s": elapsed,
                    "complete_pipeline_fps": len(frames) / elapsed,
                    "process_cpu_s": cpu,
                    "peak_rss_mib": max(memory or [process.memory_info().rss]) / 1048576,
                    "observed_torch_threads": torch.get_num_threads(),
                    "machine_cpu_percent_before": machine_load,
                    "accuracy": accuracy(frames, result),
                    "safety_scope": "physical calibration absent; safety gate remains disabled",
                    "result_sha256": sha(config.DATA / "results" / f"{identity}.json"),
                }
            )
            print(
                "Repeated complete pipeline",
                repetition,
                tracker,
                round(elapsed, 2),
                "s",
                runs[-1]["accuracy"],
                flush=True,
            )
            del result
    summaries = []
    for tracker in ("bytetrack.yaml", "botsort.yaml"):
        selected = [r for r in runs if r["tracker"] == tracker]
        summaries.append(
            {
                "tracker": tracker,
                "runs": len(selected),
                "median_wall_s": float(
                    np.median([r["complete_pipeline_wall_s"] for r in selected])
                ),
                "aggregate_fps": sum(r["frames"] for r in selected)
                / sum(r["complete_pipeline_wall_s"] for r in selected),
                "wall_min_max_s": [
                    min(r["complete_pipeline_wall_s"] for r in selected),
                    max(r["complete_pipeline_wall_s"] for r in selected),
                ],
                "accuracy_idf1_range": [
                    min(r["accuracy"]["idf1"] for r in selected),
                    max(r["accuracy"]["idf1"] for r in selected),
                ],
            }
        )
    artifact = {
        "schema_version": "atlas-cv-end-to-end-repeat-5.0",
        "protocol_sha256": sha(protocol_path),
        "evaluator_sha256": sha(__file__),
        "model_sha256": sha(config.MODEL),
        "input_video_sha256": sha(clip),
        "source_sha256": {
            name: sha(name)
            for name in [
                "backend/atlas/pipeline.py",
                "backend/atlas/detector.py",
                "backend/atlas/analytics.py",
            ]
        },
        "hardware": {
            "cpu": platform.processor(),
            "logical_cores": psutil.cpu_count(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "device": "cpu",
        },
        "runs": runs,
        "summaries": summaries,
        "production_promoted": False,
        "limitations": protocol["limitations"],
    }
    Path("artifacts/cities/v5/cv-runtime.json").write_text(
        json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
