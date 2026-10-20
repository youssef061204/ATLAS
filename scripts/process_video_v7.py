"""Execute the frozen candidate through the full production ATLAS video pipeline."""

import argparse
import hashlib
import json
import shutil
from importlib.metadata import version
from pathlib import Path

import cv2
import torch
from atlas import config, db
from atlas.api import register_video
from atlas.detector import YOLOTracker
from atlas.pipeline import process_video
from atlas.schemas import CameraConfig
from ultralytics.utils import torch_utils

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sequence", choices=["lankershim", "peachtree-noon"], default="lankershim"
    )
    args = parser.parse_args()
    frozen = json.loads((ROOT / "docs/perception-v7-frozen.json").read_text())
    for path, digest in frozen["sources_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen perception source changed: {path}")
    source = ROOT / (
        "data/reality-v6/lankershim-camera4-0830am-0845am.avi"
        if args.sequence == "lankershim"
        else "data/reality-v7/official-videos/peachtree-camera5-1245pm-0100pm.avi"
    )
    provenance = json.loads(source.with_suffix(".avi.source.json").read_text())
    with source.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != provenance["sha256"]:
            raise ValueError("Source checksum mismatch")
    config.DATA = ROOT / "data/reality-v7" / f"production-{args.sequence}"
    for path in [config.DATA, config.DATA / "uploads", config.DATA / "results"]:
        path.mkdir(parents=True, exist_ok=True)
    if (config.DATA / "run.json").exists():
        raise FileExistsError("Never overwrite a completed full production run")
    shutil.copyfile(ROOT / "data/visdrone-yolov8n.pt", config.DATA / "visdrone-yolov8n.pt")
    config.DEVICE = "cpu"
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch_utils.NUM_THREADS = 2
    cv2.setNumThreads(1)
    settings = CameraConfig(**frozen["camera_config"])
    db.init()
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
            detections = super().infer(frame)
            self.count += 1
            if self.count % 500 == 0:
                print(
                    json.dumps(
                        {
                            "sequence": args.sequence,
                            "actual_consecutive_frames": self.count,
                            "tracks": len(detections),
                        }
                    ),
                    flush=True,
                )
            return detections

    print(
        json.dumps(
            {
                "starting_complete_production_run": identity,
                "sequence": args.sequence,
                "camera": settings.model_dump(),
                "frozen_before_test_scoring": True,
            }
        ),
        flush=True,
    )
    result = process_video(identity, ProgressTracker)
    if (
        result["performance"]["decoded_frames"] != result["metadata"]["frame_count"]
        or result["performance"]["processed_frames"] != result["metadata"]["frame_count"]
    ):
        raise ValueError("Full consecutive-frame processing is mandatory")
    result_path = config.DATA / "results" / f"{identity}.json"
    record = {
        "video_id": identity,
        "sequence": args.sequence,
        "result_file": str(result_path),
        "result_sha256": hashlib.file_digest(result_path.open("rb"), "sha256").hexdigest(),
        "performance": result["performance"],
        "summary": result["summary"],
        "source_sha256": provenance["sha256"],
        "frozen_sha256": hashlib.sha256(
            (ROOT / "docs/perception-v7-frozen.json").read_bytes()
        ).hexdigest(),
        "dependencies": {
            name: version(name)
            for name in ["ultralytics", "torch", "numpy", "opencv-python", "scipy"]
        },
        "scope": "Complete production ATLAS pipeline on real raw video, CPU, every consecutive frame. Physical calibration/evaluation is separate. Historical prerecorded data, not a live feed.",
    }
    (config.DATA / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    publication = ROOT / "artifacts/reality/v7" / f"complete-production-{args.sequence}.json"
    publication.write_bytes(
        json.dumps({k: v for k, v in record.items() if k != "result_file"}, indent=2).encode()
    )
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
