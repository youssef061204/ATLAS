"""Real UA-DETRAC evaluation of pretrained YOLO and the production tracker adapter."""

import json
import time
from importlib.metadata import version
from pathlib import Path

import cv2
import numpy as np
import psutil
from scipy.optimize import linear_sum_assignment

from atlas import config
from atlas.analytics import TrajectoryEngine
from atlas.detector import YOLOTracker
from atlas.evaluation.artifacts import checksum, write_artifact
from atlas.evaluation.data import DATASETS, parse_detrac_csv
from atlas.geometry import Projection
from atlas.schemas import CameraConfig

VEHICLES = {"car", "motorcycle", "bus", "truck"}


def overlap(a, b, denominator="union"):
    a, b = np.asarray(a, dtype=float).reshape(-1, 4), np.asarray(b, dtype=float).reshape(-1, 4)
    intersection = np.maximum(
        0, np.minimum(a[:, None, 2:], b[None, :, 2:]) - np.maximum(a[:, None, :2], b[None, :, :2])
    ).prod(axis=2)
    aa, ba = (a[:, 2:] - a[:, :2]).prod(axis=1), (b[:, 2:] - b[:, :2]).prod(axis=1)
    divisor = (
        aa[:, None] if denominator == "prediction" else aa[:, None] + ba[None, :] - intersection
    )
    return intersection / np.maximum(divisor, 1e-12)


def matches(gt, predictions, threshold=0.5):
    similarities = overlap([o["bbox"] for o in gt], [o["bbox"] for o in predictions])
    rows, columns = linear_sum_assignment(-((similarities >= threshold) * 1000 + similarities))
    return [
        (int(i), int(j))
        for i, j in zip(rows, columns, strict=True)
        if similarities[i, j] >= threshold
    ]


def ignore_predictions(gt, predictions, ignored):
    if not ignored or not predictions:
        return predictions
    protected = {j for _, j in matches(gt, predictions)}
    ioa = overlap([o["bbox"] for o in predictions], ignored, "prediction")
    return [p for j, p in enumerate(predictions) if j in protected or not (ioa[j] > 0.5).any()]


def tracking_input(frames, predictions):
    gt_ids = {
        identity: index
        for index, identity in enumerate(sorted({o["id"] for f in frames for o in f["objects"]}))
    }
    pred_ids = {
        identity: index
        for index, identity in enumerate(sorted({o["id"] for f in predictions for o in f}))
    }
    return {
        "num_timesteps": len(frames),
        "num_gt_ids": len(gt_ids),
        "num_tracker_ids": len(pred_ids),
        "num_gt_dets": sum(len(f["objects"]) for f in frames),
        "num_tracker_dets": sum(map(len, predictions)),
        "gt_ids": [np.array([gt_ids[o["id"]] for o in f["objects"]], dtype=int) for f in frames],
        "tracker_ids": [np.array([pred_ids[o["id"]] for o in f], dtype=int) for f in predictions],
        "similarity_scores": [
            overlap([o["bbox"] for o in f["objects"]], [o["bbox"] for o in p])
            for f, p in zip(frames, predictions, strict=True)
        ],
    }


def coco_ground_truth(sequence_frames):
    images, annotations, mapping = [], [], {}
    for sequence, frames in sequence_frames.items():
        for f in frames:
            image_id = len(images) + 1
            mapping[(sequence, f["frame"])] = image_id
            images.append(
                {
                    "id": image_id,
                    "width": f["width"],
                    "height": f["height"],
                    "file_name": f"{sequence}/{f['filename']}",
                }
            )
            for box, crowd in [(o["bbox"], 0) for o in f["objects"]] + [
                (box, 1) for box in f["ignored"]
            ]:
                x1, y1, x2, y2 = box
                annotations.append(
                    {
                        "id": len(annotations) + 1,
                        "image_id": image_id,
                        "category_id": 1,
                        "bbox": [x1, y1, x2 - x1, y2 - y1],
                        "area": (x2 - x1) * (y2 - y1),
                        "iscrowd": crowd,
                    }
                )
    return {
        "info": {"description": "UA-DETRAC predeclared subset, vehicle merged category"},
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": "vehicle"}],
    }, mapping


def evaluate_detection(ground_truth, detections):
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    coco = COCO()
    coco.dataset = ground_truth
    coco.createIndex()
    if detections:
        prediction = coco.loadRes(detections)
    else:
        prediction = COCO()
        prediction.dataset = {**ground_truth, "annotations": []}
        prediction.createIndex()
    evaluator = COCOeval(coco, prediction, "bbox")
    evaluator.evaluate()
    evaluator.accumulate()
    evaluator.summarize()
    return {
        "map50_95": float(evaluator.stats[0]),
        "map50": float(evaluator.stats[1]),
        "per_class_ap": {"vehicle": float(evaluator.stats[0])},
    }


def evaluate_vision(split="test", resolution=640, confidence=0.25, variant="baseline", reuse=False):
    import trackeval

    root = DATASETS / "ua-detrac"
    manifest = json.loads((root / "manifest.json").read_text())
    sequence_frames = {
        s["sequence"]: json.loads((root / split / s["sequence"] / "frames.json").read_text())
        for s in manifest["splits"][split]
    }
    ground_truth, image_ids = coco_ground_truth(sequence_frames)
    output = DATASETS / "evaluation-runs" / f"detrac-{split}-{variant}-{resolution}-{confidence}"
    output.mkdir(parents=True, exist_ok=True)
    detector_records, tracking_records, analytics, performance = [], {}, {}, []
    trackeval_metrics = [
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR(),
        trackeval.metrics.Identity(),
    ]
    metric_scores = {metric.get_name(): {} for metric in trackeval_metrics}
    settings = CameraConfig(
        resolution=resolution, confidence=confidence, sample_every=1, tracker="bytetrack.yaml"
    )
    for sequence, frames in sequence_frames.items():
        folder = root / split / sequence
        source = next(s for s in manifest["splits"][split] if s["sequence"] == sequence)
        if checksum(folder / "annotations.csv") != source["annotation_sha256"]:
            raise ValueError("Annotation checksum mismatch")
        if frames != list(parse_detrac_csv(folder / "annotations.csv", len(frames)).values()):
            raise ValueError("Converted annotations differ from verified source")
        for frame in frames:
            if checksum(folder / frame["filename"]) != source["image_sha256"][frame["filename"]]:
                raise ValueError("Evaluation image checksum mismatch")
        cache = output / f"{sequence}.json"
        # Cached predictions are reusable only with the exact images, settings, and weights.
        adapter = YOLOTracker(settings)
        weight_path = Path(adapter.model.ckpt_path)
        model_sha = checksum(weight_path)
        signature = {
            "manifest_sha256": checksum(root / "manifest.json"),
            "model_sha256": model_sha,
            "settings": settings.model_dump(),
            "sequence": sequence,
            "ultralytics": version("ultralytics"),
        }
        if reuse and cache.exists():
            cached = json.loads(cache.read_text())
            if cached["signature"] != signature:
                raise ValueError("Prediction cache provenance mismatch; rerun without --reuse")
            detections, tracks, perf = cached["detections"], cached["tracks"], cached["performance"]
        else:
            detections, tracks, latencies, detector_latency = [], [], [], []
            process = psutil.Process()
            cpu_before = sum(process.cpu_times()[:2])
            started = time.perf_counter()
            memory_peak = process.memory_info().rss
            # A separate model keeps AP's low-confidence predictions out of tracker state.
            from ultralytics import YOLO

            detector = YOLO(config.MODEL)
            vehicle_ids = [i for i, name in detector.names.items() if name in VEHICLES]
            for f in frames:
                path = folder / f["filename"]
                expected = next(s for s in manifest["splits"][split] if s["sequence"] == sequence)[
                    "image_sha256"
                ][f["filename"]]
                if checksum(path) != expected:
                    raise ValueError("Evaluation image checksum mismatch")
                image = cv2.imread(str(path))
                if image is None:
                    raise ValueError(f"Cannot decode {path}")
                before = time.perf_counter()
                boxes = detector.predict(
                    image,
                    conf=0.001,
                    iou=0.7,
                    imgsz=resolution,
                    classes=vehicle_ids,
                    device=config.DEVICE,
                    verbose=False,
                )[0].boxes
                detector_latency.append((time.perf_counter() - before) * 1000)
                detections.append(
                    [
                        {"bbox": list(map(float, box)), "confidence": float(score)}
                        for box, score in zip(
                            boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy(), strict=True
                        )
                    ]
                )
                before = time.perf_counter()
                observations = [o for o in adapter.infer(image) if o["class"] in VEHICLES]
                latencies.append((time.perf_counter() - before) * 1000)
                tracks.append(ignore_predictions(f["objects"], observations, f["ignored"]))
                memory_peak = max(memory_peak, process.memory_info().rss)
            wall = time.perf_counter() - started
            cpu_seconds = sum(process.cpu_times()[:2]) - cpu_before
            perf = {
                "frames": len(frames),
                "wall_seconds": wall,
                "detector_fps": len(frames) / (sum(detector_latency) / 1000),
                "detector_tracker_fps": len(frames) / (sum(latencies) / 1000),
                "detector_inference_ms": {
                    f"p{q}": float(np.percentile(detector_latency, q)) for q in [50, 95, 99]
                },
                "detector_tracker_ms": {
                    f"p{q}": float(np.percentile(latencies, q)) for q in [50, 95, 99]
                },
                "tracking_wall_seconds": sum(latencies) / 1000,
                "cpu_process_percent": cpu_seconds / wall * 100,
                "cpu_machine_capacity_percent": cpu_seconds / wall / psutil.cpu_count() * 100,
                "memory_peak_rss_mb": memory_peak / 1024**2,
            }
            cache.write_text(
                json.dumps(
                    {
                        "signature": signature,
                        "detections": detections,
                        "tracks": tracks,
                        "performance": perf,
                    }
                )
            )
        performance.append({"sequence": sequence, **perf})
        engine = TrajectoryEngine(Projection(None), [])
        counts, gt_counts = [], []
        tp, fp, fn = 0, 0, 0
        for f, det, tracked in zip(frames, detections, tracks, strict=True):
            image_id = image_ids[(sequence, f["frame"])]
            for d in det:
                x1, y1, x2, y2 = d["bbox"]
                detector_records.append(
                    {
                        "image_id": image_id,
                        "category_id": 1,
                        "bbox": [x1, y1, x2 - x1, y2 - y1],
                        "score": d["confidence"],
                    }
                )
            thresholded = ignore_predictions(
                f["objects"], [d for d in det if d["confidence"] >= confidence], f["ignored"]
            )
            matched = len(matches(f["objects"], thresholded))
            tp += matched
            fp += len(thresholded) - matched
            fn += len(f["objects"]) - matched
            _, metric = engine.update((f["frame"] - 1) / manifest["fps"], tracked)
            counts.append(metric["vehicles"])
            gt_counts.append(len(f["objects"]))
        tracking_records[sequence] = {"tp": tp, "fp": fp, "fn": fn}
        data = tracking_input(frames, tracks)
        for metric in trackeval_metrics:
            metric_scores[metric.get_name()][sequence] = metric.eval_sequence(data)
        error = np.asarray(counts) - gt_counts
        analytics[sequence] = {
            "frames": len(frames),
            "active_vehicle_count_mae": float(np.abs(error).mean()),
            "active_vehicle_count_rmse": float(np.sqrt((error**2).mean())),
            "mean_ground_truth_vehicles": float(np.mean(gt_counts)),
            "predicted_unique_tracks": engine.summary()["unique_tracks"],
            "ground_truth_unique_tracks": data["num_gt_ids"],
            "unique_track_relative_error_pct": abs(
                engine.summary()["unique_tracks"] - data["num_gt_ids"]
            )
            / max(data["num_gt_ids"], 1)
            * 100,
            "preview": [
                {"frame": f["frame"], "actual": a, "predicted": p}
                for f, a, p in zip(frames, gt_counts, counts, strict=True)
            ][::10],
        }
        print(
            f"Evaluated {sequence}: {len(frames)} frames, {data['num_gt_ids']} annotated trajectories",
            flush=True,
        )
    detection_metrics = evaluate_detection(ground_truth, detector_records)
    totals = {key: sum(s[key] for s in tracking_records.values()) for key in ["tp", "fp", "fn"]}
    precision, recall = (
        totals["tp"] / max(totals["tp"] + totals["fp"], 1),
        totals["tp"] / max(totals["tp"] + totals["fn"], 1),
    )
    detection_metrics.update(
        precision=precision,
        recall=recall,
        f1=2 * precision * recall / max(precision + recall, 1e-12),
        **totals,
    )
    tracking_metrics = {}
    for metric in trackeval_metrics:
        combined = metric.combine_sequences(metric_scores[metric.get_name()])
        for key in [
            "HOTA",
            "DetA",
            "AssA",
            "IDF1",
            "MOTA",
            "MOTP",
            "IDSW",
            "CLR_FP",
            "CLR_FN",
            "Frag",
        ]:
            if key in combined:
                tracking_metrics[key] = float(np.mean(combined[key]))
    metadata = dict(
        data_provenance="real",
        dataset="UA-DETRAC",
        dataset_version=manifest["revision"],
        model=f"{config.MODEL} + ByteTrack",
        split={
            "official_partition": "test" if split == "test" else "train (validation only)",
            "sequences": list(sequence_frames),
            "frames_per_sequence": {s: len(f) for s, f in sequence_frames.items()},
            "training": "none; pretrained weights",
            "selection": manifest["protocol"],
        },
        scope="Real annotated traffic, predeclared UA-DETRAC subset. Not a full UA-DETRAC challenge score or its PR-MOTA protocol.",
        methodology={
            "settings": settings.model_dump(),
            "model_sha256": model_sha,
            "ultralytics": version("ultralytics"),
            "class_mapping": manifest["class_mapping"],
            "ignore_policy": "COCO crowd IoA for detection AP; tracking removes unmatched predictions with ignored-region IoA > 0.5 after valid GT matching at IoU 0.5",
            "detection_ap": "pycocotools COCOeval, conf floor 0.001, NMS IoU 0.7, IoU 0.50:0.05:0.95, maxDets=100",
            "precision_recall": f"confidence {confidence}, class-merged maximum-cardinality matching at IoU 0.5",
            "tracking": "Production YOLOTracker.infer, all frames, new persistent tracker per sequence; TrackEval official combine_sequences",
        },
    )
    suffix = "" if variant == "baseline" and split == "test" else f"_{split}_{variant}"
    write_artifact(
        "real_detection" + suffix, benchmark_type="detection", metrics=detection_metrics, **metadata
    )
    write_artifact(
        "real_tracking" + suffix,
        benchmark_type="tracking",
        metrics=tracking_metrics,
        results={
            "sequences": {
                sequence: {
                    key: float(np.mean(value))
                    for metric in trackeval_metrics
                    for key, value in metric_scores[metric.get_name()][sequence].items()
                }
                for sequence in sequence_frames
            }
        },
        **metadata,
    )
    write_artifact(
        "real_analytics" + suffix,
        benchmark_type="traffic_analytics",
        metrics={
            "active_vehicle_count_mae": float(
                np.average(
                    [s["active_vehicle_count_mae"] for s in analytics.values()],
                    weights=[s["frames"] for s in analytics.values()],
                )
            ),
            "active_vehicle_count_rmse": float(
                np.sqrt(
                    np.average(
                        [s["active_vehicle_count_rmse"] ** 2 for s in analytics.values()],
                        weights=[s["frames"] for s in analytics.values()],
                    )
                )
            ),
        },
        results={
            "sequences": analytics,
            "unvalidated": [
                "physical speed",
                "queue length",
                "directional/crossing counts (no declared virtual gates)",
                "physical occupancy",
            ],
        },
        **metadata,
    )
    total_frames = sum(p["frames"] for p in performance)
    tracking_seconds = sum(p["tracking_wall_seconds"] for p in performance)
    write_artifact(
        "real_video_systems" + suffix,
        benchmark_type="systems",
        metrics={
            "frames": total_frames,
            "detector_tracker_fps": total_frames / tracking_seconds,
            "seconds_per_minute_video": tracking_seconds / (total_frames / manifest["fps"]) * 60,
            "tracking_inference_seconds": tracking_seconds,
            "evaluation_wall_seconds": sum(p["wall_seconds"] for p in performance),
            "memory_peak_rss_mb": max(p["memory_peak_rss_mb"] for p in performance),
            "safety_events_per_second": None,
        },
        results={"sequences": performance},
        **{
            **metadata,
            "scope": "Actual real annotated frames. Separate detector and production detector+tracker passes; wall/RSS/CPU include both passes. No GPU or calibrated safety-event throughput claim.",
        },
    )
    (output / "coco-ground-truth.json").write_text(json.dumps(ground_truth))
    (output / "coco-predictions.json").write_text(json.dumps(detector_records))
    return {"detection": detection_metrics, "tracking": tracking_metrics}
