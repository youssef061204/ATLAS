"""Measured degradation sensitivity on pinned real images; no weather claim."""

import contextlib
import io
import json
import time
from pathlib import Path

import cv2
import numpy as np
import psutil
import torch
from atlas.cities import now
from atlas.city_network import sha
from atlas.evaluation.artifacts import hardware
from atlas.evaluation.vision import (
    VEHICLES,
    coco_ground_truth,
    evaluate_detection,
    ignore_predictions,
    matches,
)
from ultralytics import YOLO


def transform(image, condition):
    if condition == "unaltered":
        return image
    if condition == "brightness_0.35":
        return np.round(image.astype(float) * 0.35).astype(np.uint8)
    if condition == "gaussian_blur_9_sigma3":
        return cv2.GaussianBlur(image, (9, 9), 3)
    if condition == "half_resolution_restore":
        h, w = image.shape[:2]
        return cv2.resize(cv2.resize(image, (w // 2, h // 2)), (w, h))
    if condition == "jpeg_quality20":
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 20])
        if not ok:
            raise ValueError("Failed controlled JPEG encoding")
        return cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    raise ValueError("Unknown registered degradation")


def main():
    protocol_path = Path("docs/cv-robustness-protocol.json")
    p = json.loads(protocol_path.read_text())
    root = Path("datasets/ua-detrac")
    manifest = json.loads((root / "manifest.json").read_text())
    torch.set_num_threads(p["threads"])
    model = YOLO("yolo11n.pt")
    classes = [i for i, name in model.names.items() if name in VEHICLES]
    sources = {}
    for sequence in manifest["splits"]["test"]:
        folder = root / "test" / sequence["sequence"]
        frames = json.loads((folder / "frames.json").read_text())[: p["frames_per_camera"]]
        if sha(folder / "annotations.csv") != sequence["annotation_sha256"]:
            raise ValueError("Annotation provenance mismatch")
        for frame in frames:
            if sha(folder / frame["filename"]) != sequence["image_sha256"][frame["filename"]]:
                raise ValueError("Image provenance mismatch")
        sources[sequence["sequence"]] = frames
    ground, image_ids = coco_ground_truth(sources)
    results = []
    for condition in p["conditions"]:
        records = []
        tp = fp = fn = 0
        latencies = []
        cpu_start = sum(psutil.Process().cpu_times()[:2])
        for sequence, frames in sources.items():
            for frame in frames:
                image = transform(
                    cv2.imread(str(root / "test" / sequence / frame["filename"])), condition
                )
                tick = time.perf_counter()
                prediction = model.predict(
                    image,
                    imgsz=640,
                    conf=0.001,
                    iou=0.7,
                    classes=classes,
                    device="cpu",
                    verbose=False,
                )[0]
                latencies.append((time.perf_counter() - tick) * 1000)
                objects = [
                    {"bbox": box.xyxy[0].tolist(), "confidence": float(box.conf[0])}
                    for box in prediction.boxes
                ]
                objects = ignore_predictions(frame["objects"], objects, frame["ignored"])
                filtered = [o for o in objects if o["confidence"] >= 0.25]
                matched = len(matches(frame["objects"], filtered))
                tp += matched
                fp += len(filtered) - matched
                fn += len(frame["objects"]) - matched
                for obj in objects:
                    x1, y1, x2, y2 = obj["bbox"]
                    records.append(
                        {
                            "image_id": image_ids[(sequence, frame["frame"])],
                            "category_id": 1,
                            "bbox": [x1, y1, x2 - x1, y2 - y1],
                            "score": obj["confidence"],
                        }
                    )
        with contextlib.redirect_stdout(io.StringIO()):
            score = evaluate_detection(ground, records)
        score.update(
            precision=tp / max(1, tp + fp), recall=tp / max(1, tp + fn), tp=tp, fp=fp, fn=fn
        )
        result = {
            "condition": condition,
            "metrics": score,
            "frames": len(latencies),
            "model_prediction_ms_p50": float(np.percentile(latencies, 50)),
            "model_prediction_ms_p95": float(np.percentile(latencies, 95)),
            "cpu_seconds": sum(psutil.Process().cpu_times()[:2]) - cpu_start,
        }
        results.append(result)
        print(condition, score, flush=True)
    output = {
        "experiment_id": p["experiment_id"],
        "recorded_at": now(),
        "protocol_sha256": sha(protocol_path),
        "manifest_sha256": sha(root / "manifest.json"),
        "model_sha256": sha("yolo11n.pt"),
        "source_sha256": sha(__file__),
        "hardware": hardware(),
        "results": results,
        "scope": p["scope"],
        "limitations": [
            "Three camera prefixes, not full sequences or all challenge cameras",
            "Brightness, blur, resolution and JPEG changes are controlled synthetic conditions; natural weather is not validated",
            "Prediction timing includes model pre/postprocessing; excludes ingest, tracking and persistence",
            "Independent city-camera and pedestrian/cyclist accuracy remain unmeasured",
        ],
    }
    Path("artifacts/cities/perception-robustness.json").write_text(
        json.dumps(output, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
