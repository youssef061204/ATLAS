"""Run consecutive real frames with frozen candidate settings; never read test labels."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v7"
PROFILES = {
    "v8-ocsort": ("data/visdrone-yolov8n.pt", 960, 0.10, "ocsort.yaml"),
    "v8-botsort": ("data/visdrone-yolov8n.pt", 960, 0.10, "botsort.yaml"),
    "v11n-coco": ("yolo11n.pt", 960, 0.10, "bytetrack.yaml"),
    "v11s-coco": ("yolo11s.pt", 960, 0.10, "bytetrack.yaml"),
    "v8-tiles": ("data/visdrone-yolov8n.pt", 960, 0.10, "multiscale_v7.ByteTrack"),
    "v8-recall": ("data/visdrone-yolov8n.pt", 960, 0.05, "docs/bytetrack-v7-recall.yaml"),
    "v8-recall-high-resolution": (
        "data/visdrone-yolov8n.pt",
        1280,
        0.05,
        "docs/bytetrack-v7-recall.yaml",
    ),
    "v6-replication": ("data/visdrone-yolov8n.pt", 960, 0.15, "bytetrack.yaml"),
    "v8-high-resolution": ("data/visdrone-yolov8n.pt", 1280, 0.10, "bytetrack.yaml"),
    "v11s-aerial": ("data/visdrone-yolo11s.pt", 960, 0.10, "bytetrack.yaml"),
    "v11s-recall": ("data/visdrone-yolo11s.pt", 960, 0.05, "docs/bytetrack-v7-recall.yaml"),
    "v11s-botsort": ("data/visdrone-yolo11s.pt", 960, 0.05, "botsort.yaml"),
    "v11s-ocsort": ("data/visdrone-yolo11s.pt", 960, 0.05, "ocsort.yaml"),
}


def main():
    executed_source = Path(__file__).read_bytes()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--start", type=int, default=60)
    parser.add_argument("--end", type=int, default=180)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if not 0 <= args.start < args.end <= 1000:
        raise ValueError("Development runner cannot access reserved temporal test")
    import torch
    from atlas.detector import CLASS_MAP, TRAFFIC_CLASSES
    from ultralytics import YOLO
    from ultralytics.utils import torch_utils

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch_utils.NUM_THREADS = args.threads
    cv2.setNumThreads(1)
    weights, size, confidence, tracker = PROFILES[args.profile]
    weights = ROOT / weights
    if not weights.exists():
        raise FileNotFoundError(f"Acquire pinned research weight first: {weights.name}")
    directory = DATA / f"{args.profile}-{args.start}-{args.end}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "executed-runner.py").write_bytes(executed_source)
    output = directory / "frames.jsonl.gz"
    if output.exists():
        raise FileExistsError("Preserve completed experiment; choose a separate interval/profile")
    model = YOLO(weights)
    tiled = None
    if args.profile == "v8-tiles":
        from atlas.multiscale_v7 import MultiScaleTracker

        tiled = MultiScaleTracker(model, size, confidence)
        (directory / "executed-multiscale.py").write_bytes(
            (ROOT / "backend/atlas/multiscale_v7.py").read_bytes()
        )
    classes = [i for i, name in model.names.items() if CLASS_MAP.get(name, name) in TRAFFIC_CLASSES]
    source = ROOT / "data/reality-v6/lankershim-camera4-0830am-0845am.avi"
    capture = cv2.VideoCapture(str(source))
    capture.set(cv2.CAP_PROP_POS_FRAMES, args.start * 10)
    started = time.perf_counter()
    inference, rss, count = [], 0, 0
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        for index in range(args.start * 10, args.end * 10):
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"Incomplete source decoding at {index}")
            before = time.perf_counter()
            result = (
                None
                if tiled
                else model.track(
                    frame,
                    persist=True,
                    tracker=str(ROOT / tracker) if "/" in tracker else tracker,
                    classes=classes,
                    conf=confidence,
                    imgsz=size,
                    device="cpu",
                    verbose=False,
                )[0]
            )
            inference.append((time.perf_counter() - before) * 1000)
            objects = []
            if tiled:
                objects = tiled.infer(frame)
            elif result.boxes is not None and result.boxes.id is not None:
                for box, identity, cls, conf in zip(
                    result.boxes.xyxy.tolist(),
                    result.boxes.id.tolist(),
                    result.boxes.cls.tolist(),
                    result.boxes.conf.tolist(),
                    strict=True,
                ):
                    name = model.names[int(cls)]
                    objects.append(
                        {
                            "id": int(identity),
                            "class": CLASS_MAP.get(name, name),
                            "confidence": float(conf),
                            "bbox": box,
                        }
                    )
            inference[-1] = (time.perf_counter() - before) * 1000
            handle.write(
                json.dumps({"index": index, "objects": objects}, separators=(",", ":")) + "\n"
            )
            count += 1
            rss = max(rss, psutil.Process().memory_info().rss)
            if count % 200 == 0:
                print(
                    json.dumps(
                        {
                            "profile": args.profile,
                            "processed": count,
                            "of": (args.end - args.start) * 10,
                        }
                    ),
                    flush=True,
                )
    capture.release()
    wall = time.perf_counter() - started
    record = {
        "status": "complete",
        "profile": args.profile,
        "window_s": [args.start, args.end],
        "source": source.name,
        "source_sha256": hashlib.file_digest(source.open("rb"), "sha256").hexdigest(),
        "weights": weights.name,
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "resolution": size,
        "confidence": confidence,
        "tracker": tracker,
        "torch_threads": torch.get_num_threads(),
        "decoded_frames": count,
        "processed_frames": count,
        "wall_seconds": wall,
        "fps": count / wall,
        "inference_ms": {f"p{p}": float(np.percentile(inference, p)) for p in [50, 95, 99]},
        "peak_rss_mb": rss / 1024**2,
        "cuda_available": torch.cuda.is_available(),
        "frames_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(executed_source).hexdigest(),
        "scope": "Same consecutive-frame development workload. Model selection uses independent development annotations only; not a complete-recording or holdout benchmark.",
    }
    (directory / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
