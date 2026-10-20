"""Development-only Peachtree image/world registration with temporal check points."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v7/peachtree"
ORIGIN = np.array([2230500.0, 1375700.0])
SCALE = 1200 / 3937
ORIGIN_SECONDS = 1163018700


def development():
    cache = DATA / "development-reference.csv.gz"
    if cache.exists():
        return pd.read_csv(cache)
    source = DATA / "support/NGSIM_Peachtree_Vehicle_Trajectories.csv"
    columns = [
        "Vehicle_ID",
        "Frame_ID",
        "Global_Time",
        "Local_X",
        "Local_Y",
        "Global_X",
        "Global_Y",
        "v_length",
        "v_Vel",
        "Lane_ID",
        "Section_ID",
        "Direction",
        "Movement",
        "Int_ID",
    ]
    frames = []
    for rows in pd.read_csv(source, usecols=columns, chunksize=50000):
        keep = (rows.Global_Time - (rows.Frame_ID - 1) * 100 == ORIGIN_SECONDS) & (
            rows.Frame_ID <= 3001
        )
        frames.append(rows[keep])
    result = pd.concat(frames, ignore_index=True).sort_values(["Vehicle_ID", "Frame_ID"])
    if result.duplicated(["Vehicle_ID", "Frame_ID"]).any():
        raise ValueError("Duplicate reference states")
    result.to_csv(cache, index=False, compression="gzip")
    return result


def body_centers(rows):
    # The supplied speed column is audited separately; derive heading from a
    # longer source-position difference rather than assuming a zero speed means
    # a vehicle is stopped or trusting a noisy one-frame direction.
    xy = (rows[["Global_X", "Global_Y"]].to_numpy() - ORIGIN) * SCALE
    past = rows.groupby("Vehicle_ID")[["Global_X", "Global_Y"]].diff(10).to_numpy()
    norms = np.linalg.norm(past, axis=1)
    heading = np.column_stack(
        [np.zeros(len(rows)), np.where(rows.Direction.to_numpy() == 4, -1.0, 1.0)]
    )
    valid = np.isfinite(norms) & (norms > 3.0)
    heading[valid] = past[valid] / norms[valid, None]
    return xy - rows.v_length.to_numpy()[:, None] * SCALE * 0.5 * heading


def main():
    rows = development()
    centers = body_centers(rows)
    rows["cx"], rows["cy"] = centers.T
    # Hand-read centres of actual source footprint rectangles in frame 600.
    # Annotated video is registration reference only; raw pixels feed the model.
    controls = {
        65: [169, 127],
        66: [273, 136],
        67: [238, 155],
        68: [345, 156],
        69: [449, 164],
        70: [522, 164],
        73: [133, 205],
        77: [62, 175],
    }
    checks = {
        53: [65, 160],
        95: [54, 182],
        103: [118, 183],
        88: [133, 204],
        182: [199, 132],
        181: [291, 186],
        116: [375, 138],
        118: [415, 139],
        112: [398, 162],
        120: [465, 161],
        137: [471, 140],
        125: [533, 166],
    }
    control = []
    for identity, pixel in controls.items():
        source = rows[(rows.Vehicle_ID == identity) & (rows.Frame_ID == 601)]
        if len(source) != 1:
            raise ValueError(f"Missing development control {identity}")
        point = source[["cx", "cy"]].to_numpy()[0]
        control.append(
            {
                "id": identity,
                "processed_pixel": pixel,
                "world_body_m": point.tolist(),
                "role": "spatial_check" if identity in {67, 77} else "fit",
            }
        )
    fitted = [p for p in control if p["role"] == "fit"]
    rectified, _ = cv2.findHomography(
        np.float64([p["processed_pixel"] for p in fitted]),
        np.float64([p["world_body_m"] for p in fitted]),
        method=0,
    )
    alignment = json.loads((DATA / "development-time-alignment.json").read_text())
    if {row["offset_frames"] for row in alignment["development_frames"]} != {4}:
        raise ValueError("Development source-clock registration is inconsistent")
    capture = cv2.VideoCapture(
        str(ROOT / "data/reality-v7/official-videos/peachtree-camera1-1245pm-0100pm.avi")
    )
    capture.set(cv2.CAP_PROP_POS_FRAMES, 604)
    ok, source_pixels = capture.read()
    capture.release()
    if not ok:
        raise ValueError("Aligned development raw frame did not decode")
    raw = cv2.cvtColor(source_pixels, cv2.COLOR_BGR2GRAY)
    processed = cv2.imread(str(DATA / "processed-development-600.jpg"), cv2.IMREAD_GRAYSCALE)
    sift = cv2.SIFT_create(nfeatures=6000)
    # Coarse road-plane alignment from visible crosswalk corners compensates
    # for the strong stretch/rotation before independent SIFT refinement.
    rough = cv2.getPerspectiveTransform(
        np.float32([[272, 229], [352, 225], [294, 309], [377, 302]]),
        np.float32([[319, 143], [314, 215], [159, 118], [157, 196]]),
    )
    prewarped = cv2.warpPerspective(raw, rough, (640, 344))
    ka, da = sift.detectAndCompute(prewarped, None)
    kb, db = sift.detectAndCompute(processed, None)
    matches = [
        a for a, b in cv2.BFMatcher().knnMatch(da, db, k=2) if a.distance < 0.75 * b.distance
    ]
    source = np.float32([ka[m.queryIdx].pt for m in matches])
    target = np.float32([kb[m.trainIdx].pt for m in matches])
    registration, inliers = cv2.findHomography(source, target, cv2.RANSAC, 2.5)
    if inliers is None or inliers.sum() < 12:
        raise ValueError("Insufficient raw-to-reference registration support")
    registration = registration @ rough
    matrix = rectified @ registration
    for p in control:
        estimate = cv2.perspectiveTransform(np.float64([[p["processed_pixel"]]]), rectified)[0, 0]
        p["residual_m"] = float(np.linalg.norm(estimate - p["world_body_m"]))
    temporal = []
    for identity, pixel in checks.items():
        actual = rows[(rows.Vehicle_ID == identity) & (rows.Frame_ID == 1201)]
        if len(actual) != 1:
            continue
        estimated = cv2.perspectiveTransform(np.float64([[pixel]]), rectified)[0, 0]
        point = actual[["cx", "cy"]].to_numpy()[0]
        temporal.append(
            {
                "id": identity,
                "frame_index": 1200,
                "processed_pixel": pixel,
                "error_m": float(np.linalg.norm(estimated - point)),
            }
        )
    record = {
        "scope": "Development-only calibration and checks at 60 s and 120 s. No held-out annotations read.",
        "clock_origin_seconds": ORIGIN_SECONDS,
        "raw_frame_offset": 4,
        "registration_raw_frame": 604,
        "registration_reference_frame": 600,
        "reference_time_rule": "t=(Frame_ID-1)/10. Supplied Global_Time mixes seconds origin and millisecond increments; never interpret it directly as an epoch timestamp.",
        "global_origin_survey_ft": ORIGIN.tolist(),
        "survey_ft_to_m": SCALE,
        "raw_to_world": matrix.tolist(),
        "raw_to_rectified": registration.tolist(),
        "rectified_to_world": rectified.tolist(),
        "registration_matches": len(matches),
        "registration_inliers": int(inliers.sum()),
        "controls": control,
        "spatial_check_rmse_m": float(
            np.sqrt(
                np.mean([p["residual_m"] ** 2 for p in control if p["role"] == "spatial_check"])
            )
        ),
        "temporal_checks": temporal,
        "temporal_check_rmse_m": float(np.sqrt(np.mean([p["error_m"] ** 2 for p in temporal]))),
        "reference_speed_column_development": {
            "rows": len(rows),
            "zero_fraction": float((rows.v_Vel == 0).mean()),
            "nonzero_rows": int((rows.v_Vel != 0).sum()),
        },
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limitations": [
            "Manual footprint centre reading and approximate front-to-body heading",
            "Calibration diagnostics are not video tracking or physical simulation accuracy",
            "Additional source-time alignment check is required before scoring independent data",
        ],
    }
    (DATA / "calibration-development.json").write_bytes(json.dumps(record, indent=2).encode())
    print(
        json.dumps(
            {
                key: record[key]
                for key in [
                    "registration_matches",
                    "registration_inliers",
                    "spatial_check_rmse_m",
                    "temporal_check_rmse_m",
                    "temporal_checks",
                    "reference_speed_column_development",
                ]
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
