"""Visualize independent reference POINTS and actual detections on development pixels."""

import gzip
import json

import cv2
import numpy as np
from diagnose_ngsim_v7 import DATA, ROOT, development_observations
from reconstruct_ngsim_v6 import METRES, ORIGIN, road_model
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree


def main():
    observations = development_observations(180)
    road, _ = road_model(observations)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    tree = cKDTree(curve)
    normals = np.gradient(curve, axis=0)[:, ::-1] * [1, -1]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    matrix = np.array(json.loads((DATA / "camera4-calibration.json").read_text())["raw_to_world"])
    inverse = np.linalg.inv(matrix)
    world = (observations[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    past = observations.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    magnitude = np.linalg.norm(past, axis=1)
    _, nearest = tree.query(world)
    headings = np.gradient(curve, axis=0)[nearest]
    headings /= np.linalg.norm(headings, axis=1)[:, None]
    headings *= np.where(observations.direction.to_numpy() == 4, -1, 1)[:, None]
    valid = np.isfinite(magnitude) & (magnitude > 0.01)
    headings[valid] = past[valid] / magnitude[valid, None]
    centers = world - observations.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * headings
    _, nearest = tree.query(centers)
    lateral = np.sum((centers - curve[nearest]) * normals[nearest], axis=1)
    keep = (
        (grid[nearest] >= 1090)
        & (grid[nearest] <= 1360)
        & (abs(lateral) <= 16)
        & observations.direction.isin([2, 4]).to_numpy()
        & observations.lane_id.between(1, 4).to_numpy()
    )
    observations["cx"], observations["cy"] = centers.T
    desired = {65, 70, 90, 120, 150, 175}
    predictions = {}
    with gzip.open(ROOT / "data/reality-v7/v6-replication-60-180/frames.jsonl.gz", "rt") as handle:
        for line in handle:
            frame = json.loads(line)
            if frame["index"] / 10 in desired:
                predictions[frame["index"] / 10] = frame["objects"]
    capture = cv2.VideoCapture(str(DATA / "lankershim-camera4-0830am-0845am.avi"))
    images = []
    records = []
    for t in sorted(desired):
        actual = observations[keep & (observations.t == t)]
        points = actual[["cx", "cy"]].to_numpy()
        pixels = cv2.perspectiveTransform(points.reshape(1, -1, 2), inverse)[0]
        objects = [o for o in predictions[t] if o["class"] in {"car", "truck", "bus", "motorcycle"}]
        predicted_pixels = np.array(
            [
                [(o["bbox"][0] + o["bbox"][2]) / 2, (o["bbox"][1] + o["bbox"][3]) / 2]
                for o in objects
            ]
        )
        predicted = (
            cv2.perspectiveTransform(predicted_pixels.reshape(1, -1, 2), matrix)[0]
            if len(objects)
            else np.empty((0, 2))
        )
        distances = np.linalg.norm(points[:, None] - predicted[None, :], axis=2)
        ii, jj = linear_sum_assignment(np.where(distances <= 4, distances, 1e6))
        matched = {i for i, j in zip(ii, jj, strict=True) if distances[i, j] <= 4}
        capture.set(cv2.CAP_PROP_POS_FRAMES, t * 10)
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("Source frame did not decode")
        image = cv2.copyMakeBorder(image, 35, 30, 0, 0, cv2.BORDER_CONSTANT, value=(20, 28, 32))
        for o in objects:
            x1, y1, x2, y2 = map(round, o["bbox"])
            cv2.rectangle(image, (x1, y1 + 35), (x2, y2 + 35), (120, 200, 140), 1)
        outside = 0
        for i, ((u, v), identity) in enumerate(zip(pixels, actual.vehicle_id, strict=True)):
            if not 0 <= u < 640 or not 0 <= v < 480:
                outside += 1
                continue
            color = (120, 220, 120) if i in matched else (100, 100, 255)
            cv2.drawMarker(image, (round(u), round(v) + 35), color, cv2.MARKER_CROSS, 12, 2)
            cv2.putText(
                image,
                f"GT {identity}",
                (round(u) + 5, round(v) + 31),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                color,
                1,
            )
        cv2.putText(
            image,
            f"{t}s | {len(points)} reference points | {len(matched)} matched | {outside} outside image",
            (10, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (230, 235, 235),
            1,
        )
        cv2.putText(
            image,
            "Actual boxes; crosses are independent world centers projected through estimated H",
            (9, 533),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.37,
            (210, 220, 225),
            1,
        )
        images.append(image)
        records.append(
            {
                "time_s": t,
                "reference": len(points),
                "matched": len(matched),
                "outside_image": outside,
            }
        )
    capture.release()
    out = ROOT / "artifacts/reality/v7"
    cv2.imwrite(
        str(out / "development-point-misses.jpg"),
        np.vstack([np.hstack(images[:3]), np.hstack(images[3:])]),
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    )
    (out / "development-point-misses.json").write_bytes(
        json.dumps(
            {
                "scope": "Development diagnostic, not test results or annotated bounding boxes",
                "frames": records,
            },
            indent=2,
        ).encode()
    )
    print(json.dumps(records), flush=True)


if __name__ == "__main__":
    main()
