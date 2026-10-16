"""Independent point-trajectory evaluation, never synthetic bounding-box labels."""

import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import trackeval
from atlas.reality_v6 import matched_errors
from reconstruct_ngsim_v6 import DATA, METRES, ORIGIN, load_observations, road_model
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

VEHICLES = {"car", "truck", "bus", "motorcycle"}
GATE_M = 4.0


def main():
    observations = load_observations()
    road, geometry = road_model(observations)
    grid = np.linspace(960, 1410, 1801)
    curve = road(grid)
    normal = np.gradient(curve, axis=0)[:, ::-1] * [1, -1]
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    tree = cKDTree(curve)

    def roi(points):
        if len(points) == 0:
            return np.array([], dtype=bool)
        _, nearest = tree.query(points)
        lateral = np.sum((points - curve[nearest]) * normal[nearest], axis=1)
        return (grid[nearest] >= 1090) & (grid[nearest] <= 1360) & (abs(lateral) <= 16)

    # Ground-truth body center from independently annotated front point and length.
    xy = (observations[["global_x", "global_y"]].to_numpy() - ORIGIN) * METRES
    past = observations.groupby("vehicle_id")[["global_x", "global_y"]].diff().to_numpy()
    magnitude = np.linalg.norm(past, axis=1)
    _, nearest = tree.query(xy)
    fallback = np.gradient(curve, axis=0)[nearest]
    fallback /= np.linalg.norm(fallback, axis=1)[:, None]
    fallback *= np.where(observations.direction.to_numpy() == 4, -1, 1)[:, None]
    valid = np.isfinite(magnitude) & (magnitude > 0.01)
    heading = fallback
    heading[valid] = past[valid] / magnitude[valid, None]
    centers = xy - observations.v_length.to_numpy()[:, None] * 0.3048 * 0.5 * heading
    observations["center_x"], observations["center_y"] = centers.T
    selected = (
        (observations.t >= 600)
        & (observations.t < 1000)
        & (observations.global_time % 1000 == 0)
        & observations.direction.isin([2, 4])
        & observations.lane_id.between(1, 4)
        & roi(centers)
    )
    truth = {round(t): group for t, group in observations[selected].groupby("t")}
    run_path = DATA / "production-pipeline/run.json"
    if not run_path.exists():
        run_path = DATA / "production-pipeline/run-development.json"
    run = json.loads(run_path.read_text())
    result_path = Path(run["result_file"])
    result = json.loads(result_path.read_text())
    if result["performance"]["processed_frames"] != 11220 or result["config"]["sample_every"] != 1:
        raise ValueError(
            "This protocol requires the complete 11,220-frame raw development recording"
        )
    calibration = json.loads((DATA / "camera4-calibration.json").read_text())
    matrix = np.array(calibration["raw_to_world"])
    trails = defaultdict(deque)
    predictions = {}
    for frame in result["frames"]:
        time = frame["index"] / 10
        rows = []
        for obj in frame["objects"]:
            if obj["class"] not in VEHICLES:
                continue
            x1, y1, x2, y2 = obj["bbox"]
            point = cv2.perspectiveTransform(
                np.float64([[[0.5 * (x1 + x2), 0.5 * (y1 + y2)]]]), matrix
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
            if frame["index"] % 10 == 0 and 600 <= time < 1000:
                rows.append({"id": obj["id"], "point": point, "speed": speed})
        if frame["index"] % 10 == 0 and 600 <= time < 1000:
            inside = roi(np.array([r["point"] for r in rows]))
            predictions[round(time)] = [r for r, keep in zip(rows, inside, strict=True) if keep]
    gt_ids = sorted(set(observations[selected].vehicle_id))
    pred_ids = sorted({r["id"] for rows in predictions.values() for r in rows})
    gt_index = {identity: i for i, identity in enumerate(gt_ids)}
    pred_index = {identity: i for i, identity in enumerate(pred_ids)}
    values = {
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
        "num_gt_ids": len(gt_ids),
        "num_tracker_ids": len(pred_ids),
        "num_gt_dets": 0,
        "num_tracker_dets": 0,
    }
    distances, speeds, estimates, count_observed, count_estimated = [], [], [], [], []
    per_frame = []
    for time in range(600, 1000):
        actual = truth[time].to_dict("records") if time in truth else []
        predicted = predictions.get(time, [])
        a = np.array([[r["center_x"], r["center_y"]] for r in actual]).reshape(-1, 2)
        b = np.array([r["point"] for r in predicted]).reshape(-1, 2)
        distance = np.linalg.norm(a[:, None] - b[None, :], axis=2)
        values["gt_ids"].append(np.array([gt_index[r["vehicle_id"]] for r in actual], dtype=int))
        values["tracker_ids"].append(np.array([pred_index[r["id"]] for r in predicted], dtype=int))
        values["similarity_scores"].append((distance <= GATE_M).astype(float))
        values["num_gt_dets"] += len(actual)
        values["num_tracker_dets"] += len(predicted)
        eligible = distance <= GATE_M
        # Maximize feasible pair count before minimizing their distances.
        ii, jj = linear_sum_assignment(np.where(eligible, distance, 1e6))
        matches = [(i, j) for i, j in zip(ii, jj, strict=True) if eligible[i, j]]
        for i, j in matches:
            distances.append(float(distance[i, j]))
            speeds.append(float(actual[i]["v_vel"]) * 0.3048)
            estimates.append(predicted[j]["speed"])
        count_observed.append(len(actual))
        count_estimated.append(len(predicted))
        per_frame.append(
            {
                "t": time,
                "reference_visible_vehicles": len(actual),
                "cv_visible_vehicles": len(predicted),
                "matched": len(matches),
            }
        )
    identity = trackeval.metrics.Identity({"THRESHOLD": 0.5, "PRINT_CONFIG": False}).eval_sequence(
        values
    )
    artifact = {
        "status": "development-recording validation only; final holdout not scored",
        "window_s": [600, 1000],
        "sample_cadence_hz": 1,
        "frames_evaluated": 400,
        "source_vehicle_ids": len(gt_ids),
        "predicted_track_ids": len(pred_ids),
        "identity": {
            "metric": "Point-trajectory IDF1 with a 4 metre world-center distance gate, not bounding-box IDF1 or a UA-DETRAC-comparable result",
            **{key: float(identity[key]) for key in ["IDF1", "IDP", "IDR", "IDTP", "IDFP", "IDFN"]},
        },
        "spatial_matching": {
            "gate_m": GATE_M,
            "reference_observations": values["num_gt_dets"],
            "predicted_observations": values["num_tracker_dets"],
            "pairs": len(distances),
            "reference_coverage": len(distances) / values["num_gt_dets"]
            if values["num_gt_dets"]
            else None,
            "position_mae_m_within_gate": float(np.mean(distances)) if distances else None,
            "position_error_scope": "Conditional on distance-matched pairs; unmatched observations and gate must be considered alongside this error",
        },
        "speed_mps_matched_pairs": matched_errors(speeds, estimates),
        "instantaneous_vehicle_count": matched_errors(count_observed, count_estimated),
        "count_scope": "Instantaneous vehicles in a fixed road-space observation region; not crossing flow/count accuracy",
        "roi": "Nearest development-fitted road median parameter 1090–1360 local ft; lateral +/-16 m; body centers. Source lane 1–4, directions NB/SB. The source annotations do not independently label per-camera occlusion; occluded vehicles can contribute misses.",
        "calibration_validation_rmse_m": calibration["validation_rmse_m"],
        "limitations": [
            "One camera/date, one validation interval; no final held-out result",
            "No independent detection boxes: no mAP or conventional box tracking benchmark claimed",
            "Manual development calibration, approximate road-space ROI and vehicle roof parallax",
            "This artifact measures perception only. Separate CV-driven SUMO artifacts report aggregate count/queue/travel-time errors; turn/lane accuracy, physical queue-tail length and paired individual travel times remain unvalidated",
        ],
        "geometry": geometry,
        "per_frame": per_frame,
        "input_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "calibration_sha256": hashlib.sha256(
            (DATA / "camera4-calibration.json").read_bytes()
        ).hexdigest(),
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    destination = DATA / "cv-validation.json"
    destination.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in artifact.items() if k not in ["per_frame", "geometry"]}, indent=2
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
