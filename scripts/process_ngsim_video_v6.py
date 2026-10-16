"""Execute the production ATLAS CV pipeline on a complete raw NGSIM recording."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import torch
from atlas import config, db
from atlas.api import register_video
from atlas.detector import YOLOTracker
from atlas.pipeline import process_video
from atlas.schemas import CameraConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sequence", choices=["development", "holdout", "holdout-prefix"], default="development"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root / "docs/ngsim-v6-protocol.json").read_text())
    period = "0830am-0845am" if args.sequence == "development" else "0845am-0900am"
    source = root / f"data/reality-v6/lankershim-camera4-{period}.avi"
    if args.sequence == "holdout-prefix":
        source = root / "data/reality-v6/lankershim-camera4-holdout-prefix.avi"
    source_record = json.loads(source.with_suffix(".avi.source.json").read_text())
    with source.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != source_record["sha256"]:
            raise ValueError("Source video checksum mismatch")
    config.DATA = root / "data/reality-v6/production-pipeline"
    for path in [config.DATA, config.DATA / "uploads", config.DATA / "results"]:
        path.mkdir(parents=True, exist_ok=True)
    cached_weights = root / "data/visdrone-yolov8n.pt"
    if cached_weights.exists():
        shutil.copyfile(cached_weights, config.DATA / cached_weights.name)
    config.DEVICE = protocol["perception"]["device"]
    torch.set_num_threads(protocol["perception"]["torch_threads"])
    cv2.setNumThreads(1)
    db.init()
    settings = CameraConfig(
        detector_profile="aerial",
        tracker="bytetrack.yaml",
        resolution=960,
        confidence=0.15,
        sample_every=1,
    )
    identity = register_video(source, source.name, "demo")
    with db.connection() as conn:
        conn.execute(
            "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
            (settings.model_dump_json(), identity),
        )

    class ProgressTracker(YOLOTracker):
        def __post_init__(self):
            super().__post_init__()
            self.count = 0

        def infer(self, frame):
            result = super().infer(frame)
            self.count += 1
            if self.count % 500 == 0:
                print(
                    "Processed consecutive raw frames",
                    self.count,
                    "current tracks",
                    len(result),
                    flush=True,
                )
            return result

    print("Starting complete video", identity, settings.model_dump(), flush=True)
    result = process_video(identity, ProgressTracker)
    if result["performance"]["decoded_frames"] != result["metadata"]["frame_count"]:
        failure = {
            "video_id": identity,
            "source_file": source.name,
            "source_archive_crc_verified": True,
            "declared_frames": result["metadata"]["frame_count"],
            "decoded_frames": result["performance"]["decoded_frames"],
            "status": "incomplete source or decoder failure; not a complete-video benchmark",
            "result_file": str(config.DATA / "results" / f"{identity}.json"),
        }
        (config.DATA / f"failure-{args.sequence}.json").write_text(
            json.dumps(failure, indent=2), encoding="utf-8"
        )
        db.status(
            identity,
            "failed",
            "source_integrity",
            0,
            error="Declared and decoded source frame counts differ; incomplete result is not eligible as a complete-video run",
        )
        raise ValueError(
            "Incomplete decoding: declared and actual frame counts differ; investigate source integrity"
        )
    record = {
        "video_id": identity,
        "result_file": str(config.DATA / "results" / f"{identity}.json"),
        "performance": result["performance"],
        "summary": result["summary"],
        "calibration": "Not yet applied; production image-plane trajectories require separate v6 physical registration and evaluation",
    }
    (config.DATA / f"run-{args.sequence}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    if args.sequence == "development":
        (config.DATA / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
