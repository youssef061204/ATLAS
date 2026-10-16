"""Complete four-camera zero-shot CV and offline cross-camera association pilot.

Raw CityFlow data, crops, embeddings and predictions remain local under its
noncommercial research license. Only aggregate evaluation is published.
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import torch
import trackeval
from atlas import config, db
from atlas.api import register_video
from atlas.detector import YOLOTracker
from atlas.multicamera_v6 import AppearanceTracklet, associate
from atlas.pipeline import process_video
from atlas.schemas import CameraConfig
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v6/cityflow-v2"
CAMERAS = ["c006", "c007", "c008", "c009"]


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def complete_pipeline(camera, protocol):
    source = DATA / f"validation/S02/{camera}/vdo.avi"
    original = json.loads(source.with_suffix(".avi.source.json").read_text())
    assert original["zip_crc_verified"] and sha(source) == original["sha256"]
    settings = CameraConfig(
        sample_every=1,
        resolution=640,
        confidence=0.25,
        tracker="bytetrack.yaml",
        detector_profile="coco",
    )
    cache = config.DATA / f"{camera}-run.json"
    inputs = {
        "source_sha256": sha(source),
        "model_sha256": sha(Path(config.MODEL)),
        "settings": settings.model_dump(),
        "pipeline_sha256": sha(ROOT / "backend/atlas/pipeline.py"),
        "detector_sha256": sha(ROOT / "backend/atlas/detector.py"),
    }
    if cache.exists():
        previous = json.loads(cache.read_text())
        if previous.get("inputs") == inputs and Path(previous["result_file"]).exists():
            result = json.loads(Path(previous["result_file"]).read_text())
            if result["performance"]["decoded_frames"] == protocol["expected_frames"][camera]:
                print("Verified complete cached processing", camera, flush=True)
                return result, previous
    identity = register_video(source, f"CityFlowV2-S02-{camera}.avi", "demo")
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
            objects = super().infer(frame)
            self.count += 1
            if self.count % 500 == 0:
                print(camera, self.count, "consecutive frames", flush=True)
            return objects

    result = process_video(identity, Progress)
    expected = protocol["expected_frames"][camera]
    if (
        result["performance"]["decoded_frames"] != expected
        or result["performance"]["processed_frames"] != expected
    ):
        db.status(
            identity,
            "failed",
            "source_integrity",
            0,
            error="CityFlow declared/decoded frame mismatch",
        )
        raise ValueError(f"Incomplete CityFlow video: {camera}")
    record = {
        "camera": camera,
        "result_file": str(config.DATA / "results" / f"{identity}.json"),
        "inputs": inputs,
        "performance": result["performance"],
        "resolution": [result["metadata"]["width"], result["metadata"]["height"]],
    }
    cache.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(
        "Complete actual CV pipeline",
        camera,
        expected,
        "frames",
        result["performance"]["processed_fps"],
        "FPS",
        flush=True,
    )
    return result, record


def appearances(camera, result, offset, model):
    roi = cv2.imread(str(DATA / f"validation/S02/{camera}/roi.jpg"), cv2.IMREAD_GRAYSCALE)
    if roi is None:
        raise ValueError("Missing official camera ROI")
    candidates = []
    requests = defaultdict(list)
    for track in result["tracks"]:
        points = track["points"]
        if track["class"] not in {"car", "truck", "bus", "motorcycle"} or len(points) < 3:
            continue
        areas, support = [], []
        for point in points:
            x1, y1, x2, y2 = point["bbox"]
            areas.append((x2 - x1) * (y2 - y1))
            x, y = int((x1 + x2) / 2), int((y1 + y2) / 2)
            support.append(0 <= x < roi.shape[1] and 0 <= y < roi.shape[0] and roi[y, x] > 127)
        if np.median(areas) < 1000 or np.mean(support) < 0.5:
            continue
        index = len(candidates)
        candidates.append(
            {
                "camera": camera,
                "id": track["id"],
                "start": points[0]["t"] + offset,
                "end": points[-1]["t"] + offset,
                "points": points,
            }
        )
        for sample in np.unique(
            np.linspace(0, len(points) - 1, min(4, len(points))).round().astype(int)
        ):
            point = points[sample]
            requests[round(point["t"] * 10)].append((index, point["bbox"]))
    capture = cv2.VideoCapture(str(DATA / f"validation/S02/{camera}/vdo.avi"))
    crops, owners, decoded, repeats, previous = [], [], 0, 0, None
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        fingerprint = hashlib.sha256(frame.data).digest()
        repeats += fingerprint == previous
        previous = fingerprint
        for owner, box in requests.get(decoded, []):
            x1, y1, x2, y2 = box
            crop = frame[
                max(0, int(y1)) : min(frame.shape[0], int(np.ceil(y2))),
                max(0, int(x1)) : min(frame.shape[1], int(np.ceil(x2))),
            ]
            if crop.size:
                crops.append(cv2.resize(crop, (128, 128)))
                owners.append(owner)
        decoded += 1
    capture.release()
    if decoded != result["performance"]["decoded_frames"]:
        raise ValueError("Appearance pass did not decode the same complete video")
    features = defaultdict(list)
    for start in range(0, len(crops), 16):
        embeddings = model.embed(crops[start : start + 16], imgsz=128, device="cpu", verbose=False)
        for owner, vector in zip(owners[start : start + 16], embeddings, strict=True):
            value = vector.detach().cpu().numpy().astype(float)
            features[owner].append(value / max(np.linalg.norm(value), 1e-12))
    tracks = []
    for index, candidate in enumerate(candidates):
        if not features[index]:
            continue
        candidate["embedding"] = np.mean(features[index], axis=0)
        tracks.append(candidate)
    print(
        "Appearance features",
        camera,
        len(tracks),
        "tracklets",
        len(crops),
        "actual video crops",
        flush=True,
    )
    return (
        tracks,
        {
            "consecutive_identical_source_frames": repeats,
            "appearance_pass_frames": decoded,
            "crop_samples": len(crops),
        },
        roi,
    )


def iou(a, b):
    a, b = np.array(a, dtype=float).reshape(-1, 4), np.array(b, dtype=float).reshape(-1, 4)
    intersection = np.maximum(
        0, np.minimum(a[:, None, 2:], b[None, :, 2:]) - np.maximum(a[:, None, :2], b[None, :, :2])
    ).prod(axis=2)
    union = (
        (a[:, 2:] - a[:, :2]).prod(axis=1)[:, None]
        + (b[:, 2:] - b[:, :2]).prod(axis=1)[None, :]
        - intersection
    )
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def evaluate(tracks, identity_map, rois, expected, selected=None):
    # This is the first point where GT boxes or identities are read.
    annotations = {
        camera: np.loadtxt(DATA / f"validation/S02/{camera}/gt/gt.txt", delimiter=",", ndmin=2)
        for camera in CAMERAS
    }
    truth_ids = sorted({int(row[1]) for rows in annotations.values() for row in rows})
    gt_lookup = {identity: index for index, identity in enumerate(truth_ids)}
    chosen = [
        track
        for track in tracks
        if selected is None or identity_map[(track["camera"], track["id"])] in selected
    ]
    identifiers = sorted({identity_map[(track["camera"], track["id"])] for track in chosen})
    pred_lookup = {identity: index for index, identity in enumerate(identifiers)}
    predicted = defaultdict(list)
    for track in chosen:
        roi = rois[track["camera"]]
        for point in track["points"]:
            x1, y1, x2, y2 = point["bbox"]
            # Source evaluator's full-box corner ROI policy; do not clip boxes into eligibility.
            corners = [
                (int(x1), int(y1)),
                (int(x2), int(y1)),
                (int(x1), int(y2)),
                (int(x2), int(y2)),
            ]
            if any(
                0 <= x < roi.shape[1] and 0 <= y < roi.shape[0] and roi[y, x] < 255
                for x, y in corners
            ):
                continue
            frame = round(point["t"] * 10) + 1
            predicted[(track["camera"], frame)].append(
                (pred_lookup[identity_map[(track["camera"], track["id"])]], point["bbox"])
            )
    values = {
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
        "num_gt_ids": len(truth_ids),
        "num_tracker_ids": len(identifiers),
        "num_gt_dets": 0,
        "num_tracker_dets": 0,
    }
    per_camera = {}
    for camera in CAMERAS:
        truth = defaultdict(list)
        for row in annotations[camera]:
            frame, identity, x, y, width, height = row[:6]
            if not 1 <= frame <= expected[camera] or frame != int(frame):
                raise ValueError("Reference frame outside its complete source video")
            truth[int(frame)].append((gt_lookup[int(identity)], [x, y, x + width, y + height]))
        begin = len(values["gt_ids"])
        gt_count, pred_count = 0, 0
        for frame in range(1, expected[camera] + 1):
            a, b = truth[frame], predicted[(camera, frame)]
            values["gt_ids"].append(np.array([identity for identity, _ in a], dtype=int))
            values["tracker_ids"].append(np.array([identity for identity, _ in b], dtype=int))
            values["similarity_scores"].append(iou([box for _, box in a], [box for _, box in b]))
            values["num_gt_dets"] += len(a)
            values["num_tracker_dets"] += len(b)
            gt_count += len(a)
            pred_count += len(b)
        subset = {
            **values,
            "gt_ids": values["gt_ids"][begin:],
            "tracker_ids": values["tracker_ids"][begin:],
            "similarity_scores": values["similarity_scores"][begin:],
            "num_gt_dets": gt_count,
            "num_tracker_dets": pred_count,
        }
        metric = trackeval.metrics.Identity({"PRINT_CONFIG": False}).eval_sequence(subset)
        per_camera[camera] = {
            "idf1": float(metric["IDF1"]),
            "annotated_boxes": gt_count,
            "predicted_boxes": pred_count,
        }
    metric = trackeval.metrics.Identity({"PRINT_CONFIG": False}).eval_sequence(values)
    return {
        "identity": {
            key: float(metric[key]) for key in ["IDF1", "IDP", "IDR", "IDTP", "IDFP", "IDFN"]
        },
        "annotated_vehicles": len(truth_ids),
        "annotated_boxes": values["num_gt_dets"],
        "predicted_boxes": values["num_tracker_dets"],
        "camera_frame_slots": len(values["gt_ids"]),
        "per_camera": per_camera,
    }


def main():
    protocol_path = ROOT / "docs/cityflow-v6-protocol.json"
    protocol = json.loads(protocol_path.read_text())
    config.DATA = DATA / "pipeline"
    config.MODEL, config.DEVICE = str(ROOT / "yolo11n.pt"), "cpu"
    for directory in [config.DATA, config.DATA / "uploads", config.DATA / "results"]:
        directory.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    cv2.setNumThreads(1)
    db.init()
    offsets = {
        camera: float(time)
        for camera, time in (
            line.split() for line in (DATA / "cam_timestamp/S02.txt").read_text().splitlines()
        )
    }
    model = YOLO(config.MODEL)
    candidates, records, rois, audits = [], [], {}, {}
    for camera in CAMERAS:
        result, record = complete_pipeline(camera, protocol)
        tracks, audits[camera], rois[camera] = appearances(camera, result, offsets[camera], model)
        candidates.extend(tracks)
        records.append({key: value for key, value in record.items() if key != "result_file"})
    tracklets = [
        AppearanceTracklet(
            track["camera"], track["id"], track["start"], track["end"], track["embedding"]
        )
        for track in candidates
    ]
    mapping, accepted = associate(tracklets, minimum_cosine=0.85, maximum_gap_s=30)
    baseline = {(track["camera"], track["id"]): index + 1 for index, track in enumerate(candidates)}
    # Freeze the association map before evaluating independent identities.
    (DATA / "association-before-reference.json").write_text(
        json.dumps(
            {
                "mapping": [
                    [camera, identity, global_id]
                    for (camera, identity), global_id in mapping.items()
                ],
                "accepted": accepted,
                "protocol_sha256": sha(protocol_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    groups = defaultdict(set)
    for (camera, _), identity in mapping.items():
        groups[identity].add(camera)
    multicamera = {identity for identity, cameras in groups.items() if len(cameras) >= 2}
    before = evaluate(candidates, baseline, rois, protocol["expected_frames"])
    after = evaluate(candidates, mapping, rois, protocol["expected_frames"])
    filtered = evaluate(
        candidates, mapping, rois, protocol["expected_frames"], selected=multicamera
    )
    assert before["predicted_boxes"] == after["predicted_boxes"]
    artifact = {
        "schema": "atlas-cityflow-zero-shot-research-6.0",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Complete S02 four-camera research pilot; not the whole CityFlowV2 benchmark or an official leaderboard result",
        "split": "Official validation scenario, treated as untouched zero-shot transfer evaluation; no in-domain label tuning",
        "model": "Frozen pretrained YOLO11n / ByteTrack; offline pooled YOLO crop-embedding association",
        "total_decoded_and_processed_frames": sum(
            record["performance"]["decoded_frames"] for record in records
        ),
        "camera_runs": records,
        "source_audits": audits,
        "candidate_tracklets": len(candidates),
        "associated_identities": len(multicamera),
        "accepted_cross_camera_links": len(accepted),
        "before_association": before,
        "after_association_same_detections": after,
        "multicamera_filtered": filtered,
        "idf1_change_same_detections": after["identity"]["IDF1"] - before["identity"]["IDF1"],
        "limitations": [
            "Only vehicles passing through multiple cameras are annotated; these are annotation-scoped metrics, not complete visible-vehicle accuracy",
            "Single official validation scenario, no claim of general cross-city performance",
            "Source timestamps have known skipped/stuck frames; time offsets do not prove exact synchronization",
            "Appearance pooling is not a trained vehicle-ReID model; its failures remain reported",
            "No independently surveyed speeds, travel times, queues or physical simulation accuracy evaluated for CityFlow",
            "NVIDIA dataset remains local for noncommercial research; no raw data/crops/embeddings or dataset-trained model deployed",
        ],
        "source": "https://www.aicitychallenge.org/2022-data-and-evaluation/",
        "license": "https://www.aicitychallenge.org/wp-content/uploads/2022/02/Dataset-License-AIC2022.pdf",
        "protocol_sha256": sha(protocol_path),
        "evaluator_sha256": sha(Path(__file__)),
        "association_source_sha256": sha(ROOT / "backend/atlas/multicamera_v6.py"),
    }
    destination = ROOT / "artifacts/reality/v6/cityflow-results.json"
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in artifact.items()
                if key not in ["camera_runs", "source_audits"]
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
