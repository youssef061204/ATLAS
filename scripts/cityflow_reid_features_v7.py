"""Extract actual local vehicle-specific OSNet-AIN descriptors, not generic color labels."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import openvino as ov
from cityflow_research_v7 import DATA, ROOT, load, sha
from PIL import Image


def extract(scene, tracks, metadata):
    out = ROOT / f"data/reality-v7/cityflow-reid-{scene}"
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "data/reality-v7/vehicle-reid-0001/osnet_ain_x1_0_vehicle_reid.onnx"
    if sha(source) != "4aaad3e5db648618b0df3d2ff21c61323985ff9e50194c3d2edd4fb87c92d91f":
        raise ValueError("Vehicle ReID model changed")
    if (out / "features.npz").exists():
        record = json.loads((out / "run.json").read_text())
        if record["source_sha256"] != sha(Path(__file__)):
            raise ValueError("Feature extractor changed; preserve original experiment")
        values = np.load(out / "features.npz")
        return {
            (camera, int(identity)): values[f"v{i}"]
            for i, (camera, identity) in enumerate(record["keys"])
        }
    core = ov.Core()
    model = core.read_model(source)
    model.reshape([1, 3, 208, 208])
    compiled = core.compile_model(
        model,
        "CPU",
        {
            "PERFORMANCE_HINT": "LATENCY",
            "INFERENCE_NUM_THREADS": 2,
            "NUM_STREAMS": 1,
            "INFERENCE_PRECISION_HINT": ov.Type.f32,
        },
    )
    features, crop_count, decoded_count = {}, 0, 0
    for camera in sorted(metadata):
        requests, vectors = defaultdict(list), defaultdict(list)
        for track in (t for t in tracks if t["camera"] == camera):
            points = track["points"]
            for i in np.unique(
                np.linspace(0, len(points) - 1, min(4, len(points))).round().astype(int)
            ):
                p = points[i]
                requests[round(p["t"] * metadata[camera]["fps"])].append((track["id"], p["bbox"]))
        capture = cv2.VideoCapture(
            str(DATA / f"train/{scene}/{camera}/vdo.avi"),
            cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_N_THREADS, 1],
        )
        decoded = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                for identity, box in requests.get(decoded, []):
                    x1, y1, x2, y2 = box
                    crop = frame[
                        max(0, int(y1)) : min(frame.shape[0], int(np.ceil(y2))),
                        max(0, int(x1)) : min(frame.shape[1], int(np.ceil(x2))),
                    ]
                    if not crop.size:
                        continue
                    # Official original ONNX expects RGB, unnormalized pixel values.
                    # Its first operations implement learned instance normalization.
                    image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).resize(
                        (208, 208), Image.Resampling.BILINEAR
                    )
                    tensor = np.ascontiguousarray(
                        np.asarray(image).transpose(2, 0, 1)[None], dtype=np.float32
                    )
                    vector = compiled(tensor)[compiled.output(0)].reshape(-1).copy()
                    norm = np.linalg.norm(vector)
                    if vector.shape != (512,) or not np.isfinite(vector).all() or norm < 1e-8:
                        raise ValueError("Invalid vehicle descriptor")
                    vectors[identity].append(vector / norm)
                    crop_count += 1
                decoded += 1
        finally:
            capture.release()
        if decoded != metadata[camera]["frame_count"]:
            raise ValueError("Incomplete ReID source-video pass")
        decoded_count += decoded
        for identity, rows in vectors.items():
            value = np.mean(rows, axis=0)
            features[camera, identity] = value / np.linalg.norm(value)
        print(
            json.dumps(
                {
                    "scene": scene,
                    "camera": camera,
                    "actual_decoded_frames": decoded,
                    "vehicle_reid_crop_samples": sum(len(r) for r in vectors.values()),
                }
            ),
            flush=True,
        )
    keys = sorted(features)
    np.savez_compressed(
        out / "features.npz", **{f"v{i}": features[key] for i, key in enumerate(keys)}
    )
    record = {
        "keys": keys,
        "actual_crop_samples": crop_count,
        "decoded_source_frames": decoded_count,
        "model_sha256": sha(source),
        "source_sha256": sha(Path(__file__)),
        "features_sha256": sha(out / "features.npz"),
        "engine": "OpenVINO FP32 CPU, two threads",
        "scope": "Actual whole-vehicle crops from local complete CityFlow recordings; pretrained vehicle-specific ReID, no CityFlow model training. Descriptors and raw crops never published.",
    }
    (out / "run.json").write_bytes(json.dumps(record, indent=2).encode())
    return features


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=["S01", "S03"], required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    tracks, _, _, metadata, _ = load(args.scene)
    extract(args.scene, tracks, metadata)
