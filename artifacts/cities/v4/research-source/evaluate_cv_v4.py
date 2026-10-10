"""Actual complete-sequence tracker and adaptive inference comparison, separate evidence."""

import copy
import json
import platform
import time
from pathlib import Path

import cv2
import numpy as np
import psutil
import torch
import trackeval
from atlas import config
from atlas.cities import now
from atlas.city_network import sha
from atlas.detector import YOLOTracker
from atlas.evaluation.vision import VEHICLES, ignore_predictions, tracking_input
from atlas.schemas import CameraConfig
from atlas.visual_flow import analyze_tracks


def score(frames, tracks, fps):
    data = tracking_input(frames, tracks)
    scores = {}
    for metric in (
        trackeval.metrics.HOTA(),
        trackeval.metrics.CLEAR(),
        trackeval.metrics.Identity(),
    ):
        scores[metric.get_name()] = metric.eval_sequence(data)
    gt_count = np.array([len(f["objects"]) for f in frames])
    pred_count = np.array([len(f) for f in tracks])
    gates = []
    for y in (0.4, 0.6, 0.8):
        args = (frames[0]["width"], frames[0]["height"], fps, [0.05, y], [0.95, y])
        actual = analyze_tracks([f["objects"] for f in frames], *args)
        predicted = analyze_tracks(tracks, *args)
        bins = int(np.ceil(len(frames) / 60))
        for direction in ("positive", "negative"):
            counts = []
            for events in (actual, predicted):
                row = np.zeros(bins, dtype=int)
                for event in events:
                    if event["direction"] == direction:
                        row[min(bins - 1, int(event["t"] / (60 / fps)))] += 1
                counts.append(row)
            gates.append(
                {
                    "y": y,
                    "direction": direction,
                    "actual": counts[0].tolist(),
                    "predicted": counts[1].tolist(),
                    "mae": float(np.abs(counts[0] - counts[1]).mean()),
                }
            )
    return scores, {"count_mae": float(np.abs(gt_count - pred_count).mean()), "gates": gates}


def main():
    protocol_path = Path("docs/cv-v4-protocol.json")
    protocol = json.loads(protocol_path.read_text())
    protocol_hash = sha(protocol_path)
    torch.set_num_threads(protocol["torch_threads"])
    cv2.setNumThreads(1)
    root = Path("datasets/ua-detrac")
    manifest = json.loads((root / "manifest.json").read_text())
    config.DEVICE = "cpu"
    config.MODEL = protocol["model"]
    output = Path("artifacts/cities/v4")
    output.mkdir(parents=True, exist_ok=True)
    cache_root = Path("data/cv-v4")
    cache_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for candidate in protocol["candidates"]:
        metric_scores = {name: {} for name in ("HOTA", "CLEAR", "Identity")}
        sequence_rows = []
        for item in manifest["splits"]["test"]:
            sequence = item["sequence"]
            folder = root / "test" / sequence
            frames = json.loads((folder / "frames.json").read_text())
            if sha(folder / "annotations.csv") != item["annotation_sha256"]:
                raise ValueError("Independent annotation checksum mismatch")
            settings = CameraConfig(
                sample_every=1,
                confidence=protocol["confidence"],
                resolution=protocol["resolution"],
                tracker="botsort.yaml" if candidate.startswith("botsort") else "bytetrack.yaml",
            )
            adapter = YOLOTracker(settings)
            model_sha = sha(adapter.model.ckpt_path)
            process = psutil.Process()
            rss = process.memory_info().rss
            cpu_before = sum(process.cpu_times()[:2])
            started = time.perf_counter()
            tracks, latencies, sampled = [], [], []
            previous_thumbnail = None
            previous_tracks = []
            skipped = False
            for i, frame in enumerate(frames):
                path = folder / frame["filename"]
                if sha(path) != item["image_sha256"][frame["filename"]]:
                    raise ValueError("Input image checksum mismatch")
                image = cv2.imread(str(path))
                if image is None:
                    raise ValueError("Cannot decode verified image")
                thumbnail = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (64, 36)).astype(
                    float
                )
                change = (
                    float(np.abs(thumbnail - previous_thumbnail).mean())
                    if previous_thumbnail is not None
                    else float("inf")
                )
                infer = candidate != "bytetrack_adaptive" or skipped or change >= 6 or i == 0
                before = time.perf_counter()
                if infer:
                    previous_tracks = [o for o in adapter.infer(image) if o["class"] in VEHICLES]
                tracks.append(
                    ignore_predictions(
                        frame["objects"], copy.deepcopy(previous_tracks), frame["ignored"]
                    )
                )
                sampled.append(infer)
                latencies.append((time.perf_counter() - before) * 1000)
                previous_thumbnail, skipped = thumbnail, not infer
                rss = max(rss, process.memory_info().rss)
            wall = time.perf_counter() - started
            cpu = sum(process.cpu_times()[:2]) - cpu_before
            scores, utility = score(frames, tracks, manifest["fps"])
            for name, value in scores.items():
                metric_scores[name][sequence] = value
            record = {
                "sequence": sequence,
                "frames": len(frames),
                "inferred_frames": sum(sampled),
                "wall_seconds": wall,
                "process_cpu_seconds": cpu,
                "rss_peak_mib": rss / 1024**2,
                "frame_output_ms": {f"p{q}": float(np.percentile(latencies, q)) for q in (50, 95)},
                **utility,
            }
            sequence_rows.append(record)
            (cache_root / f"{candidate}-{sequence}.json").write_text(
                json.dumps(
                    {
                        "protocol_sha256": protocol_hash,
                        "model_sha256": model_sha,
                        "tracks": tracks,
                        "inferred": sampled,
                    }
                ),
                encoding="utf-8",
            )
            print(candidate, sequence, len(frames), "frames", round(wall, 2), "s", flush=True)
        metrics = {}
        for metric in (
            trackeval.metrics.HOTA(),
            trackeval.metrics.CLEAR(),
            trackeval.metrics.Identity(),
        ):
            combined = metric.combine_sequences(metric_scores[metric.get_name()])
            for key in ("HOTA", "IDF1", "IDSW", "Frag", "MOTA"):
                if key in combined:
                    metrics[key] = float(np.mean(combined[key]))
        frames_total = sum(r["frames"] for r in sequence_rows)
        metrics.update(
            visible_vehicle_count_mae=sum(r["count_mae"] * r["frames"] for r in sequence_rows)
            / frames_total,
            gate_count_mae_per_2_4s_bin=sum(
                g["mae"] * len(g["actual"]) for r in sequence_rows for g in r["gates"]
            )
            / sum(len(g["actual"]) for r in sequence_rows for g in r["gates"]),
            process_cpu_seconds=sum(r["process_cpu_seconds"] for r in sequence_rows),
            wall_seconds=sum(r["wall_seconds"] for r in sequence_rows),
            inferred_frames=sum(r["inferred_frames"] for r in sequence_rows),
            frames=frames_total,
        )
        rows.append({"candidate": candidate, "metrics": metrics, "sequences": sequence_rows})
        result = {
            "experiment_id": protocol["experiment_id"],
            "recorded_at": now(),
            "protocol_sha256": protocol_hash,
            "dataset_manifest_sha256": sha(root / "manifest.json"),
            "model_sha256": model_sha,
            "source_sha256": sha(__file__),
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "rows": rows,
            "scope": protocol["dataset"],
            "limitations": protocol["limitations"],
            "promoted": False,
        }
        (output / "perception.json").write_text(
            json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
        )
        print(candidate, metrics, flush=True)


if __name__ == "__main__":
    main()
