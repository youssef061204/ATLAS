"""Development-only image registration with explicitly audited source footprints."""

import csv
import gzip
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reality-v6"
ORIGIN = np.array([6452300.0, 1873700.0])
SURVEY_M = 1200 / 3937
# Manually inspected footprint centers in FHWA's development rectified frame 600.
# These are source annotations used only for calibration, never detector inputs.
CENTERS = {
    124: [185, 124],
    126: [97, 204],
    127: [189, 181],
    130: [192, 225],
    129: [334, 213],
    134: [491, 232],
    135: [429, 265],
    136: [550, 272],
    138: [840, 229],
    139: [681, 214],
    140: [775, 218],
    121: [398, 332],
}
VALIDATION_IDS = [126, 134, 140]


def frame(path, index):
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise ValueError("Missing development calibration frame")
    return image


def main():
    raw = frame(OUT / "lankershim-camera4-0830am-0845am.avi", 600)
    reference = frame(OUT / "lankershim-camera4-0830am-0845am-processed.avi", 600)
    detector = cv2.SIFT_create(nfeatures=6000)
    k1, d1 = detector.detectAndCompute(raw, None)
    k2, d2 = detector.detectAndCompute(reference, None)
    pairs = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    good = [a for a, b in pairs if a.distance < 0.75 * b.distance]
    a = np.float32([k1[m.queryIdx].pt for m in good])
    b = np.float32([k2[m.trainIdx].pt for m in good])
    registration, mask = cv2.findHomography(a, b, cv2.RANSAC, 2.0)
    if registration is None or mask.sum() < 30:
        raise ValueError("Insufficient static image registration")
    rows = {}
    with gzip.open(OUT / "trajectory-pages/rows-0000000.csv.gz", "rt") as handle:
        for row in csv.DictReader(handle):
            if int(row["vehicle_id"]) in CENTERS and int(row["frame_id"]) in [600, 601, 602]:
                rows[(int(row["vehicle_id"]), int(row["frame_id"]))] = row
    records = []
    for identity, center in CENTERS.items():
        observation = rows[(identity, 601)]
        front = np.array([float(observation[k]) for k in ["global_x", "global_y"]])
        velocity = np.array(
            [
                float(rows[(identity, 602)][k]) - float(rows[(identity, 600)][k])
                for k in ["global_x", "global_y"]
            ]
        )
        if np.linalg.norm(velocity) < 0.01:
            raise ValueError("Stationary control point needs an independently audited orientation")
        world = (
            front
            - float(observation["v_length"]) * 0.5 * velocity / np.linalg.norm(velocity)
            - ORIGIN
        ) * SURVEY_M
        pixel = cv2.perspectiveTransform(np.float32([[center]]), np.linalg.inv(registration))[0, 0]
        records.append(
            {
                "source_vehicle_id": identity,
                "source_frame_id": 601,
                "raw_pixel_center": pixel.tolist(),
                "world_center_m": world.tolist(),
                "role": "validation" if identity in VALIDATION_IDS else "fit",
            }
        )
    fit = [r for r in records if r["role"] == "fit"]
    matrix, _ = cv2.findHomography(
        np.array([r["raw_pixel_center"] for r in fit]),
        np.array([r["world_center_m"] for r in fit]),
        0,
    )
    if matrix is None or not np.isfinite(matrix).all():
        raise ValueError("Invalid camera calibration")
    for record in records:
        prediction = cv2.perspectiveTransform(np.float32([[record["raw_pixel_center"]]]), matrix)[
            0, 0
        ]
        record["residual_m"] = float(np.linalg.norm(prediction - record["world_center_m"]))
    artifact = {
        "method": "Development source-footprint centers and SIFT raw-to-rectified registration; no holdout fitting",
        "source_frame_index": 600,
        "source_trajectory_frame": 601,
        "source_sequence_epoch_ms": 1118935680000,
        "global_origin_survey_ft": ORIGIN.tolist(),
        "survey_ft_to_m": SURVEY_M,
        "raw_to_world": matrix.tolist(),
        "raw_to_source_rectified": registration.tolist(),
        "registration_inliers": int(mask.sum()),
        "registration_matches": len(good),
        "points": records,
        "fit_rmse_m": float(
            np.sqrt(np.mean([r["residual_m"] ** 2 for r in records if r["role"] == "fit"]))
        ),
        "validation_rmse_m": float(
            np.sqrt(np.mean([r["residual_m"] ** 2 for r in records if r["role"] == "validation"]))
        ),
        "source_annotation_accuracy": "FHWA estimated ~2 ft lateral, ~4 ft longitudinal; manual center picks and body-center conversion add uncertainty",
        "calibration_scope": "Road-plane body centers; vehicle roof parallax and camera motion are not corrected",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUT / "camera4-calibration.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact, indent=2), flush=True)


if __name__ == "__main__":
    main()
