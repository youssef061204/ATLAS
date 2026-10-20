"""Measure FP32 runtime transfer on development video before any new-site scoring."""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
import psutil
import torch
from atlas.multiscale_v7 import MultiScaleTracker
from atlas.openvino_v7 import OpenVINOModel
from ultralytics.utils import torch_utils

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=["CPU", "GPU"], required=True)
    parser.add_argument("--start", type=int, default=60)
    parser.add_argument("--end", type=int, default=180)
    args = parser.parse_args()
    if not 0 <= args.start < args.end <= 300:
        raise ValueError("Runtime selection is confined to development footage")
    torch.set_num_threads(2)
    torch_utils.NUM_THREADS = 2
    cv2.setNumThreads(1)
    profile = "v8-tiles-openvino-" + args.device.lower()
    out = ROOT / f"data/reality-v7/{profile}-{args.start}-{args.end}"
    if out.exists():
        raise FileExistsError("Preserve runtime experiment")
    out.mkdir(parents=True)
    model = OpenVINOModel(
        ROOT / "data/reality-v7/openvino/visdrone-yolov8n_openvino_model", args.device
    )
    tracker = MultiScaleTracker(model)
    source = ROOT / "data/reality-v6/lankershim-camera4-0830am-0845am.avi"
    capture = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    capture.set(cv2.CAP_PROP_POS_FRAMES, args.start * 10)
    started, latency = time.perf_counter(), []
    try:
        with gzip.open(out / "frames.jsonl.gz", "wt", encoding="utf-8") as handle:
            for i in range(args.start * 10, args.end * 10):
                ok, frame = capture.read()
                if not ok:
                    raise ValueError("Development source decode incomplete")
                before = time.perf_counter()
                objects = tracker.infer(frame)
                latency.append((time.perf_counter() - before) * 1000)
                handle.write(
                    json.dumps({"index": i, "objects": objects}, separators=(",", ":")) + "\n"
                )
                if len(latency) % 300 == 0:
                    print(
                        json.dumps({"profile": profile, "actual_frames": len(latency)}), flush=True
                    )
    finally:
        capture.release()
    elapsed = time.perf_counter() - started
    sources = [
        "scripts/benchmark_runtime_v7.py",
        "backend/atlas/openvino_v7.py",
        "backend/atlas/multiscale_v7.py",
    ]
    for name in sources:
        (out / Path(name).name).write_bytes((ROOT / name).read_bytes())
    export = json.loads((ROOT / "data/reality-v7/openvino/aerial-export.json").read_text())
    record = {
        "profile": profile,
        "window_s": [args.start, args.end],
        "frames_sha256": hashlib.sha256((out / "frames.jsonl.gz").read_bytes()).hexdigest(),
        "runtime": model.runtime(),
        "export": export,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
        },
        "processed_frames": len(latency),
        "wall_seconds": elapsed,
        "fps": len(latency) / elapsed,
        "latency_ms": {f"p{q}": float(np.percentile(latency, q)) for q in [50, 95, 99]},
        "cold_first_frame_ms": latency[0],
        "rss_mb": psutil.Process().memory_info().rss / 1024**2,
        "scope": "Actual consecutive development video, detector plus tracker only, cold graph compilation included in wall time. Not full pipeline FPS, not independent holdout. FP32 unchanged model weights, no quantization or data-label calibration.",
    }
    (out / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    print(json.dumps({k: v for k, v in record.items() if k != "export"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
