"""Independent point tracking statistics with explicit missingness and coverage."""

from collections import defaultdict

import numpy as np
import trackeval
from scipy.optimize import linear_sum_assignment

from atlas.reality_v6 import matched_errors


def evaluate_points(truth, predictions, start, end, gate_m=4.0):
    gt_ids = sorted({r["id"] for t in range(start, end) for r in truth.get(t, [])})
    pred_ids = sorted({r["id"] for t in range(start, end) for r in predictions.get(t, [])})
    gi, pi = {v: i for i, v in enumerate(gt_ids)}, {v: i for i, v in enumerate(pred_ids)}
    values = {
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
        "num_gt_ids": len(gi),
        "num_tracker_ids": len(pi),
        "num_gt_dets": 0,
        "num_tracker_dets": 0,
    }
    distances, actual_speeds, estimated_speeds, per_frame = [], [], [], []
    history = defaultdict(list)
    inferred = matched_inferred = 0
    for t in range(start, end):
        a, b = truth.get(t, []), predictions.get(t, [])
        ap, bp = (
            np.array([r["point"] for r in a]).reshape(-1, 2),
            np.array([r["point"] for r in b]).reshape(-1, 2),
        )
        distance = np.linalg.norm(ap[:, None] - bp[None, :], axis=2)
        feasible = distance <= gate_m
        values["gt_ids"].append(np.array([gi[r["id"]] for r in a], dtype=int))
        values["tracker_ids"].append(np.array([pi[r["id"]] for r in b], dtype=int))
        values["similarity_scores"].append(feasible.astype(float))
        values["num_gt_dets"] += len(a)
        values["num_tracker_dets"] += len(b)
        ii, jj = linear_sum_assignment(np.where(feasible, distance, 1e6))
        pairs = [(i, j) for i, j in zip(ii, jj, strict=True) if feasible[i, j]]
        inferred += sum(bool(r.get("inferred")) for r in b)
        matched_inferred += sum(bool(b[j].get("inferred")) for _, j in pairs)
        for i, j in pairs:
            distances.append(float(distance[i, j]))
            actual_speeds.append(a[i].get("speed"))
            estimated_speeds.append(b[j].get("speed"))
            history[a[i]["id"]].append((t, b[j]["id"]))
        per_frame.append({"t": t, "observed": len(a), "predicted": len(b), "matched": len(pairs)})
    identity = trackeval.metrics.Identity({"THRESHOLD": 0.5, "PRINT_CONFIG": False}).eval_sequence(
        values
    )
    counts = matched_errors([r["observed"] for r in per_frame], [r["predicted"] for r in per_frame])
    mean_count = float(np.mean([r["observed"] for r in per_frame]))
    return {
        "window_s": [start, end],
        "identity": {
            key: float(identity[key]) for key in ["IDF1", "IDP", "IDR", "IDTP", "IDFP", "IDFN"]
        },
        "reference_observations": values["num_gt_dets"],
        "reference_ids": len(gi),
        "predicted_observations": values["num_tracker_dets"],
        "predicted_ids": len(pi),
        "reference_coverage": len(distances) / values["num_gt_dets"]
        if values["num_gt_dets"]
        else None,
        "empty_reference_cohort": not values["num_gt_dets"],
        "matched_pairs": len(distances),
        "matched_position_mae_m": float(np.mean(distances)) if distances else None,
        "matched_speed_mps": matched_errors(actual_speeds, estimated_speeds),
        "instantaneous_count": {
            **counts,
            "reference_mean_vehicles": mean_count,
            "normalized_mae": counts["mae"] / mean_count if mean_count else None,
        },
        "predicted_inferred_observations": inferred,
        "matched_inferred_observations": matched_inferred,
        "actual_detector_observations": values["num_tracker_dets"] - inferred,
        "sampled_assignment_id_changes": sum(
            a[1] != b[1]
            for rows in history.values()
            for a, b in zip(rows[:-1], rows[1:], strict=True)
        ),
        "scope": "1 Hz fixed-region world points, 4 m gate; conditional matched errors with coverage; not bounding-box IDF1, mAP, or ungated physical prediction accuracy",
        "per_frame": per_frame,
    }
