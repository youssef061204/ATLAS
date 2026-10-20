"""Local-only CityFlow data preparation; no reference labels feed association."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from atlas.multicamera_v7 import GeoTracklet

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v6/cityflow-v2"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def world_projection(points, calibration):
    entries = dict(line.split(":", 1) for line in calibration.read_text().splitlines())

    def matrix(text):
        return np.array([[float(v) for v in row.split()] for row in text.split(";")])

    pixels = np.float64(
        [[(p["bbox"][0] + p["bbox"][2]) / 2, p["bbox"][3]] for p in points]
    ).reshape(-1, 1, 2)
    if "Intrinsic parameter matrix" in entries:
        intrinsic = matrix(entries["Intrinsic parameter matrix"])
        distortion = np.array([float(v) for v in entries["Distortion coefficients"].split()])
        pixels = cv2.undistortPoints(pixels, intrinsic, distortion, P=intrinsic)
    return cv2.perspectiveTransform(pixels, np.linalg.inv(matrix(entries["Homography matrix"])))[
        ..., 0, :
    ]


def load(scene):
    source = DATA / "train" / scene
    offsets = {
        camera: float(t)
        for camera, t in (
            line.split() for line in (DATA / f"cam_timestamp/{scene}.txt").read_text().splitlines()
        )
    }
    tracks, projected, metadata, rois, records = [], [], {}, {}, []
    for camera in sorted(p for p in source.iterdir() if p.is_dir()):
        cache = ROOT / f"data/reality-v7/cityflow-pipeline/{scene}/{camera.name}/run.json"
        record = json.loads(cache.read_text())
        result_path = Path(record["result_file"])
        if sha(result_path) != record["result_sha256"]:
            raise ValueError("Completed inference checksum mismatch")
        result = json.loads(result_path.read_text())
        expected = result["metadata"]["frame_count"]
        if (
            result["performance"]["decoded_frames"] != expected
            or result["performance"]["processed_frames"] != expected
        ):
            raise ValueError("Only complete actual inference may be evaluated")
        metadata[camera.name] = {"fps": result["metadata"]["fps"], "frame_count": expected}
        roi = cv2.imread(str(camera / "roi.jpg"), cv2.IMREAD_GRAYSCALE)
        if roi is None:
            raise ValueError("Missing official ROI")
        rois[camera.name] = roi
        records.append(
            {
                "camera": camera.name,
                "source_sha256": record["source_sha256"],
                "result_sha256": record["result_sha256"],
                "performance": record["performance"],
                "metadata": metadata[camera.name],
                "calibration_sha256": sha(camera / "calibration.txt"),
            }
        )
        for track in result["tracks"]:
            points = track["points"]
            if track["class"] not in {"car", "bus", "truck", "motorcycle"} or len(points) < 3:
                continue
            areas, support = [], []
            for p in points:
                x1, y1, x2, y2 = p["bbox"]
                areas.append((x2 - x1) * (y2 - y1))
                x, y = int((x1 + x2) / 2), int((y1 + y2) / 2)
                support.append(0 <= x < roi.shape[1] and 0 <= y < roi.shape[0] and roi[y, x] > 127)
            if np.median(areas) < 1000 or np.mean(support) < 0.5:
                continue
            tracks.append({"camera": camera.name, "id": track["id"], "points": points})
            gps = world_projection(points, camera / "calibration.txt")
            times = np.array([p["t"] + offsets[camera.name] for p in points])
            projected.append((camera.name, track["id"], times, gps))
        del result
    all_gps = np.concatenate([gps[np.isfinite(gps).all(axis=1)] for _, _, _, gps in projected])
    origin = np.median(all_gps, axis=0)
    scales = [111320, 111320 * np.cos(np.deg2rad(origin[0]))]
    geometry = []
    for camera, identity, times, gps in projected:
        xy = (gps - origin) * scales
        valid = np.isfinite(xy).all(axis=1) & (np.linalg.norm(xy, axis=1) < 1000)
        geometry.append(GeoTracklet(camera, identity, times[valid], xy[valid]))
    return tracks, geometry, rois, metadata, records


def appearances(scene, tracks, metadata):
    """Actual video crops -> bounded HSV/Lab descriptors; never redistributed."""
    cache = ROOT / f"data/reality-v7/cityflow-features-{scene}.json"
    fingerprint = hashlib.sha256(
        json.dumps(
            [(t["camera"], t["id"], t["points"]) for t in tracks], separators=(",", ":")
        ).encode()
    ).hexdigest()
    if cache.exists():
        saved = json.loads(cache.read_text())
        if saved["track_input_sha256"] != fingerprint or saved["source_sha256"] != sha(
            Path(__file__)
        ):
            raise ValueError("Appearance cache input/source changed")
        return {
            (camera, identity): np.array(feature) for camera, identity, feature in saved["features"]
        }
    features, crop_count = {}, 0
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
                crop = cv2.resize(crop, (64, 64))
                hsv, lab = (
                    cv2.cvtColor(crop, cv2.COLOR_BGR2HSV),
                    cv2.cvtColor(crop, cv2.COLOR_BGR2LAB),
                )
                hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel()
                luminance = cv2.calcHist([lab], [0], None, [16], [0, 256]).ravel()
                vector = np.sqrt(np.concatenate([hist / hist.sum(), luminance / luminance.sum()]))
                vectors[identity].append(vector / np.linalg.norm(vector))
                crop_count += 1
            decoded += 1
        capture.release()
        if decoded != metadata[camera]["frame_count"]:
            raise ValueError("Appearance pass source frame mismatch")
        for identity, rows in vectors.items():
            vector = np.mean(rows, axis=0)
            features[camera, identity] = vector / np.linalg.norm(vector)
    cache.write_bytes(
        json.dumps(
            {
                "track_input_sha256": fingerprint,
                "source_sha256": sha(Path(__file__)),
                "actual_crop_samples": crop_count,
                "features": [
                    [camera, identity, feature.tolist()]
                    for (camera, identity), feature in features.items()
                ],
                "scope": "Local noncommercial research descriptors only; not a trained vehicle-ReID model",
            }
        ).encode()
    )
    print(
        json.dumps(
            {"scene": scene, "actual_crop_samples": crop_count, "descriptor_tracks": len(features)}
        ),
        flush=True,
    )
    return features
