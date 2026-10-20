"""Complete real NGSIM video through the production pipeline with frozen FP32 Intel inference."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTED = Path(__file__).read_bytes()


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=["peachtree", "lankershim"], required=True)
    args = parser.parse_args()
    import cv2
    import torch
    from atlas import config, db
    from atlas.api import register_video
    from atlas.multiscale_v7 import MultiScaleTracker
    from atlas.openvino_v7 import OpenVINOModel
    from atlas.pipeline import process_video
    from atlas.schemas import CameraConfig
    from ultralytics.utils import torch_utils

    freeze = json.loads((ROOT / "docs/openvino-v7-frozen.json").read_text())
    for name, digest in freeze["sources_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"Frozen runtime source changed: {name}")
    perception = json.loads((ROOT / "docs/perception-v7-frozen.json").read_text())
    for name, digest in perception["sources_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f"Frozen algorithm source changed: {name}")
    export = json.loads((ROOT / "data/reality-v7/openvino/aerial-export.json").read_text())
    directory = Path(export["model_directory"])
    if export["source_sha256"] != perception["model_sha256"]:
        raise ValueError("Different learned weights")
    for name, digest in export["files_sha256"].items():
        if sha(directory / name) != digest or digest != freeze["model_files_sha256"][name]:
            raise ValueError("Exported graph/metadata changed")
    torch.set_num_threads(2)
    torch_utils.NUM_THREADS = 2
    cv2.setNumThreads(1)
    config.DEVICE = "Intel integrated GPU, OpenVINO FP32"
    config.DATA = ROOT / f"data/reality-v7/production-{args.site}-openvino-gpu"
    for path in [config.DATA, config.DATA / "results", config.DATA / "uploads"]:
        path.mkdir(parents=True, exist_ok=True)
    if (config.DATA / "run.json").exists():
        raise FileExistsError("Preserve completed production result")
    source = ROOT / (
        "data/reality-v7/official-videos/peachtree-camera1-1245pm-0100pm.avi"
        if args.site == "peachtree"
        else "data/reality-v6/lankershim-camera4-0830am-0845am.avi"
    )
    provenance = json.loads(source.with_suffix(".avi.source.json").read_text())
    if sha(source) != provenance["sha256"]:
        raise ValueError("Source video changed")
    (config.DATA / "executed-driver.py").write_bytes(EXECUTED)
    settings = CameraConfig(
        detector_profile="aerial_multiscale",
        confidence=0.1,
        resolution=960,
        sample_every=1,
        tracker="bytetrack.yaml",
    )
    db.init()
    identity = register_video(source, source.name, "demo")
    with db.connection() as conn:
        conn.execute(
            "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
            (settings.model_dump_json(), identity),
        )

    class Tracker:
        model_identifier = "YOLOv8n-VisDrone / multiscale / OpenVINO FP32 integrated GPU"

        def __init__(self, _):
            self.model = OpenVINOModel(directory, "GPU")
            self.tracker = MultiScaleTracker(self.model)
            self.count = 0

        def infer(self, frame):
            result = self.tracker.infer(frame)
            self.count += 1
            if self.count % 500 == 0:
                print(
                    json.dumps(
                        {
                            "site": args.site,
                            "actual_consecutive_frames": self.count,
                            "runtime": self.model.runtime(),
                        }
                    ),
                    flush=True,
                )
            return result

    print(
        json.dumps(
            {
                "starting_complete_run": args.site,
                "video_id": identity,
                "runtime": "FP32 OpenVINO, Intel integrated GPU; not CUDA or CPU FPS",
                "reference_labels_used": False,
            }
        ),
        flush=True,
    )
    result = process_video(identity, Tracker)
    expected = 14961 if args.site == "peachtree" else 11220
    if (
        result["performance"]["decoded_frames"] != expected
        or result["performance"]["processed_frames"] != expected
    ):
        raise ValueError("Incomplete source processing")
    path = config.DATA / "results" / f"{identity}.json"
    record = {
        "site": args.site,
        "video_id": identity,
        "result_file": str(path),
        "result_sha256": sha(path),
        "source_sha256": provenance["sha256"],
        "runtime_freeze_sha256": sha(ROOT / "docs/openvino-v7-frozen.json"),
        "performance": result["performance"],
        "metadata": result["metadata"],
        "summary": result["summary"],
        "driver_sha256": hashlib.sha256(EXECUTED).hexdigest(),
        "scope": "Complete actual production pipeline, every decoded frame, FP32 Intel integrated GPU inference. No source reference labels feed inference. Keep CPU and GPU throughput separate. Shared-host timing is not an isolated benchmark.",
    }
    (config.DATA / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    public = {k: v for k, v in record.items() if k != "result_file"}
    (ROOT / f"artifacts/reality/v7/complete-production-{args.site}-openvino-gpu.json").write_bytes(
        json.dumps(public, indent=2).encode()
    )
    print(json.dumps(public, indent=2), flush=True)


if __name__ == "__main__":
    main()
