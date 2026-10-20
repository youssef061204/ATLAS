"""Run complete additional-site recordings through frozen ATLAS backend sources."""

import argparse
import hashlib
import json
import shutil
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTED_DRIVER = Path(__file__).read_bytes()


def run(source, directory, settings, model_name, label):
    import cv2
    import torch
    from atlas import config, db
    from atlas.api import register_video
    from atlas.detector import YOLOTracker
    from atlas.pipeline import process_video
    from ultralytics.utils import torch_utils

    frozen = json.loads((ROOT / "docs/perception-v7-frozen.json").read_text())
    for path, digest in frozen["sources_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen common backend source changed: {path}")
    provenance = json.loads(source.with_suffix(source.suffix + ".source.json").read_text())
    with source.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != provenance["sha256"]:
            raise ValueError("Source checksum mismatch")
    config.DATA = directory
    config.MODEL = str(ROOT / model_name)
    config.DEVICE = "cpu"
    for path in [directory, directory / "uploads", directory / "results"]:
        path.mkdir(parents=True, exist_ok=True)
    cache = directory / "run.json"
    if cache.exists():
        previous = json.loads(cache.read_text())
        if (
            previous["source_sha256"] != provenance["sha256"]
            or previous["camera_config"] != settings.model_dump()
        ):
            raise ValueError("Cached processing inputs differ")
        with Path(previous["result_file"]).open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != previous["result_sha256"]:
                raise ValueError("Cached result checksum mismatch")
        print("Verified complete cached run", label, flush=True)
        return previous
    (directory / "executed-driver.py").write_bytes(EXECUTED_DRIVER)
    if settings.detector_profile.startswith("aerial"):
        shutil.copyfile(ROOT / "data/visdrone-yolov8n.pt", directory / "visdrone-yolov8n.pt")
    torch.set_num_threads(2)
    torch_utils.NUM_THREADS = 2
    cv2.setNumThreads(1)
    db.init()
    identity = register_video(source, source.name, "demo")
    with db.connection() as conn:
        conn.execute(
            "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
            (settings.model_dump_json(), identity),
        )

    class Progress(YOLOTracker):
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
                            "site": label,
                            "consecutive_processed_frames": self.count,
                            "tracks": len(detections),
                        }
                    ),
                    flush=True,
                )
            return detections

    print(
        json.dumps(
            {
                "starting_complete_run": label,
                "video_id": identity,
                "camera_config": settings.model_dump(),
                "reference_labels_used": False,
            }
        ),
        flush=True,
    )
    result = process_video(identity, Progress)
    if (
        result["performance"]["processed_frames"] != result["metadata"]["frame_count"]
        or result["performance"]["decoded_frames"] != result["metadata"]["frame_count"]
    ):
        raise ValueError("Incomplete consecutive-frame processing")
    result_file = directory / "results" / f"{identity}.json"
    record = {
        "site": label,
        "video_id": identity,
        "result_file": str(result_file),
        "result_sha256": hashlib.file_digest(result_file.open("rb"), "sha256").hexdigest(),
        "source_sha256": provenance["sha256"],
        "camera_config": settings.model_dump(),
        "performance": result["performance"],
        "metadata": result["metadata"],
        "summary": result["summary"],
        "driver_sha256": hashlib.sha256(EXECUTED_DRIVER).hexdigest(),
        "sources_sha256": frozen["sources_sha256"],
        "dependencies": {
            name: version(name) for name in ["torch", "ultralytics", "opencv-python", "numpy"]
        },
        "scope": "Complete actual ATLAS production CV run. No reference labels feed inference. Calibration, association and physical validation are separate stages. CPU runtime is from shared local hardware.",
    }
    cache.write_bytes(json.dumps(record, indent=2).encode())
    public = {k: v for k, v in record.items() if k != "result_file"}
    (ROOT / "artifacts/reality/v7" / f"complete-production-{label}.json").write_bytes(
        json.dumps(public, indent=2).encode()
    )
    print(
        json.dumps(
            {
                "completed": label,
                "frames": record["performance"]["processed_frames"],
                "fps": record["performance"]["processed_fps"],
            }
        ),
        flush=True,
    )
    return record


def main():
    from atlas.schemas import CameraConfig

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site", choices=["peachtree-camera1", "cityflow-S01", "cityflow-S03"], required=True
    )
    args = parser.parse_args()
    if args.site == "peachtree-camera1":
        settings = CameraConfig(
            detector_profile="aerial_multiscale",
            confidence=0.1,
            resolution=960,
            sample_every=1,
            tracker="bytetrack.yaml",
        )
        source = ROOT / "data/reality-v7/official-videos/peachtree-camera1-1245pm-0100pm.avi"
        run(
            source,
            ROOT / "data/reality-v7/production-peachtree-camera1",
            settings,
            "yolo11n.pt",
            args.site,
        )
    else:
        scene = args.site.split("-")[-1]
        source_root = ROOT / "data/reality-v6/cityflow-v2/train" / scene
        settings = CameraConfig(
            detector_profile="coco",
            confidence=0.25,
            resolution=640,
            sample_every=1,
            tracker="bytetrack.yaml",
        )
        for camera in sorted(path for path in source_root.iterdir() if path.is_dir()):
            run(
                camera / "vdo.avi",
                ROOT / "data/reality-v7/cityflow-pipeline" / scene / camera.name,
                settings,
                "yolo11n.pt",
                f"cityflow-{scene}-{camera.name}",
            )


if __name__ == "__main__":
    main()
