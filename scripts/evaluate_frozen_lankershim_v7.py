"""Frozen-window point evaluation; raw observations and offline inferred boxes stay distinct."""

import argparse
import gzip
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import trackeval
from atlas.reality_v6 import matched_errors
from diagnose_ngsim_v7 import DATA, ROOT, development_observations
from reconstruct_ngsim_v6 import METRES, ORIGIN, road_model
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree


def evaluate(directory, start, end, strict=False):
    run = json.loads((directory / "run.json").read_text())
    if (start, end) not in [(600, 1000), (1020, 1120)]:
        raise ValueError("Only predeclared regression and reserved test windows are allowed")
    if end > run["window_s"][1]:
        raise ValueError("Run does not cover the evaluation interval")
    frozen = json.loads((ROOT / "docs/perception-v7-frozen.json").read_text())
    for path, digest in frozen["sources_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source changed: {path}")
    if (
        hashlib.sha256((DATA / "camera4-calibration.json").read_bytes()).hexdigest()
        != frozen["calibration_sha256"]
    ):
        raise ValueError("Frozen calibration changed")
    observations = development_observations(end=max(300, end))
    road, _ = road_model(observations)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    normals = np.gradient(curve, axis=0)[:, ::-1] * [1, -1]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    tree = cKDTree(curve)

    def roi(points):
        points = np.asarray(points).reshape(-1, 2)
        if not len(points):
            return np.array([], dtype=bool)
        _, nearest = tree.query(points)
        lateral = np.sum((points - curve[nearest]) * normals[nearest], axis=1)
        return (grid[nearest] >= 1090) & (grid[nearest] <= 1360) & (abs(lateral) <= 16)

    world = (observations[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    past = observations.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    magnitude = np.linalg.norm(past, axis=1)
    _, nearest = tree.query(world)
    heading = np.gradient(curve, axis=0)[nearest]
    heading /= np.linalg.norm(heading, axis=1)[:, None]
    heading *= np.where(observations.direction.to_numpy() == 4, -1, 1)[:, None]
    valid = np.isfinite(magnitude) & (magnitude > 0.01)
    heading[valid] = past[valid] / magnitude[valid, None]
    centers = world - observations.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * heading
    observations["center_x"], observations["center_y"] = centers.T
    first_seen = observations.groupby("vehicle_id").t.min().to_dict()
    selected = (
        (observations.t >= start)
        & (observations.t < end)
        & (observations.global_time % 1000 == 0)
        & observations.direction.isin([2, 4])
        & observations.lane_id.between(1, 4)
        & roi(centers)
    )
    if strict:
        selected &= observations.vehicle_id.map(first_seen) >= start
    truth = {round(t): group.to_dict("records") for t, group in observations[selected].groupby("t")}
    matrix = np.asarray(json.loads((DATA / "camera4-calibration.json").read_text())["raw_to_world"])
    predictions, trails, births = {}, defaultdict(deque), {}
    with gzip.open(directory / "frames.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            frame = json.loads(line)
            time = frame["index"] / 10
            rows = []
            for obj in frame["objects"]:
                if obj["class"] not in {"car", "bus", "truck", "motorcycle"}:
                    continue
                births.setdefault(obj["id"], time)
                if strict and births[obj["id"]] < start:
                    continue
                x1, y1, x2, y2 = obj["bbox"]
                point = cv2.perspectiveTransform(
                    np.float64([[[(x1 + x2) / 2, (y1 + y2) / 2]]]), matrix
                )[0, 0]
                history = trails[obj["id"]]
                if history and time - history[-1][0] > 0.3:
                    history.clear()
                history.append((time, point))
                while history and history[0][0] < time - 0.75:
                    history.popleft()
                speed = None
                if len(history) >= 3:
                    times = np.array([r[0] for r in history])
                    values = np.array([r[1] for r in history])
                    centered = times - times.mean()
                    speed = float(
                        np.linalg.norm(
                            centered @ (values - values.mean(axis=0)) / (centered @ centered)
                        )
                    )
                rows.append(
                    {
                        "id": obj["id"],
                        "point": point,
                        "speed": speed,
                        "inferred": bool(obj.get("inferred", False)),
                    }
                )
            if start <= time < end and frame["index"] % 10 == 0:
                keep = roi([r["point"] for r in rows])
                predictions[round(time)] = [
                    r for r, inside in zip(rows, keep, strict=True) if inside
                ]
    gt_ids = sorted({r["vehicle_id"] for rows in truth.values() for r in rows})
    pred_ids = sorted({r["id"] for rows in predictions.values() for r in rows})
    gt_index, pred_index = (
        {v: i for i, v in enumerate(gt_ids)},
        {v: i for i, v in enumerate(pred_ids)},
    )
    values = {
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
        "num_gt_ids": len(gt_ids),
        "num_tracker_ids": len(pred_ids),
        "num_gt_dets": 0,
        "num_tracker_dets": 0,
    }
    distances, speeds, estimates, actual_counts, predicted_counts, per_frame = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    identity_history = defaultdict(list)
    inferred_count = inferred_matched = 0
    for time in range(start, end):
        actual, predicted = truth.get(time, []), predictions.get(time, [])
        a = np.array([[r["center_x"], r["center_y"]] for r in actual]).reshape(-1, 2)
        b = np.array([r["point"] for r in predicted]).reshape(-1, 2)
        distance = np.linalg.norm(a[:, None] - b[None, :], axis=2)
        feasible = distance <= 4
        values["gt_ids"].append(np.array([gt_index[r["vehicle_id"]] for r in actual], dtype=int))
        values["tracker_ids"].append(np.array([pred_index[r["id"]] for r in predicted], dtype=int))
        values["similarity_scores"].append(feasible.astype(float))
        values["num_gt_dets"] += len(actual)
        values["num_tracker_dets"] += len(predicted)
        ii, jj = linear_sum_assignment(np.where(feasible, distance, 1e6))
        matched = [(i, j) for i, j in zip(ii, jj, strict=True) if feasible[i, j]]
        inferred_count += sum(r["inferred"] for r in predicted)
        inferred_matched += sum(predicted[j]["inferred"] for i, j in matched)
        for i, j in matched:
            distances.append(float(distance[i, j]))
            speeds.append(float(actual[i]["v_vel"]) * 0.3048)
            estimates.append(predicted[j]["speed"])
            identity_history[actual[i]["vehicle_id"]].append((time, predicted[j]["id"]))
        actual_counts.append(len(actual))
        predicted_counts.append(len(predicted))
        per_frame.append(
            {
                "t": time,
                "observed": len(actual),
                "predicted": len(predicted),
                "matched": len(matched),
            }
        )
    identity = trackeval.metrics.Identity({"THRESHOLD": 0.5, "PRINT_CONFIG": False}).eval_sequence(
        values
    )
    report = {
        "profile": run["profile"],
        "window_s": [start, end],
        "scope": "Known regression"
        if end <= 1000
        else "Reserved temporal test, same camera/date, not independent location",
        "metric_scope": "Fixed v6 road-space ROI, 1 Hz samples, 4 m point gate; not bounding-box IDF1 or mAP",
        "cohort": "Whole tracks first observed at/after window start, for reference and predictions separately"
        if strict
        else "All eligible observations inside the fixed time window",
        "predicted_inferred_observations": inferred_count,
        "matched_inferred_observations": inferred_matched,
        "actual_detector_observations": values["num_tracker_dets"] - inferred_count,
        "identity": {
            key: float(identity[key]) for key in ["IDF1", "IDP", "IDR", "IDTP", "IDFP", "IDFN"]
        },
        "reference_observations": values["num_gt_dets"],
        "predicted_observations": values["num_tracker_dets"],
        "matched_pairs": len(distances),
        "reference_coverage": len(distances) / values["num_gt_dets"]
        if values["num_gt_dets"]
        else None,
        "empty_reference_cohort": values["num_gt_dets"] == 0,
        "empty_cohort_note": "No newly observed reference identities; strict-cohort accuracy is not estimable"
        if not values["num_gt_dets"]
        else None,
        "matched_position_mae_m": float(np.mean(distances)) if distances else None,
        "matched_speed_mps": matched_errors(speeds, estimates),
        "instantaneous_count": matched_errors(actual_counts, predicted_counts),
        "sampled_assignment_id_changes": sum(
            a[1] != b[1]
            for rows in identity_history.values()
            for a, b in zip(rows[:-1], rows[1:], strict=True)
        ),
        "assignment_scope": "Changes in per-frame spatial assignments at 1 Hz, including gaps; not conventional bounding-box MOT IDSW",
        "runtime": run,
        "per_frame": per_frame,
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output = (
        ROOT
        / "artifacts/reality/v7"
        / f"evaluation-{directory.name}-{start}-{end}{'-strict' if strict else '-window'}.json"
    )
    if output.exists():
        raise FileExistsError("Preserve completed evaluation")
    output.write_bytes(json.dumps(report, indent=2).encode())
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ["per_frame", "runtime"]}, indent=2
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    evaluate(args.directory, args.start, args.end, args.strict)
