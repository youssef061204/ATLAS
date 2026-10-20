"""Annotation-scoped multi-camera Identity evaluation with explicit source cadence.

Padding is an annotation-convention ablation, never a physical vehicle size.
The eligible raw observations stay identical across padding/association variants.
"""

from collections import defaultdict

import numpy as np
import trackeval


def padded_box(box, padding):
    if padding < 0 or not np.isfinite(padding):
        raise ValueError("Invalid annotation padding")
    return np.asarray(box, dtype=float) + [-padding, -padding, padding, padding]


def overlap(a, b):
    a, b = np.asarray(a, dtype=float).reshape(-1, 4), np.asarray(b, dtype=float).reshape(-1, 4)
    intersection = np.maximum(
        0, np.minimum(a[:, None, 2:], b[None, :, 2:]) - np.maximum(a[:, None, :2], b[None, :, :2])
    ).prod(axis=2)
    union = (
        np.maximum(a[:, 2:] - a[:, :2], 0).prod(axis=1)[:, None]
        + np.maximum(b[:, 2:] - b[:, :2], 0).prod(axis=1)[None, :]
        - intersection
    )
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def evaluate(tracks, mapping, rois, metadata, annotations, padding=0, selected=None):
    ids = sorted({int(row[1]) for rows in annotations.values() for row in rows})
    gt_index = {identity: i for i, identity in enumerate(ids)}
    chosen = [t for t in tracks if selected is None or mapping[t["camera"], t["id"]] in selected]
    pred_ids = sorted({mapping[t["camera"], t["id"]] for t in chosen})
    pred_index = {identity: i for i, identity in enumerate(pred_ids)}
    predicted = defaultdict(list)
    for track in chosen:
        camera = track["camera"]
        roi = rois[camera]
        for point in track["points"]:
            x1, y1, x2, y2 = point["bbox"]
            if any(
                0 <= x < roi.shape[1] and 0 <= y < roi.shape[0] and roi[y, x] < 255
                for x, y in [
                    (int(x1), int(y1)),
                    (int(x2), int(y1)),
                    (int(x1), int(y2)),
                    (int(x2), int(y2)),
                ]
            ):
                continue
            frame = round(point["t"] * metadata[camera]["fps"]) + 1
            if not 1 <= frame <= metadata[camera]["frame_count"]:
                raise ValueError("Predicted frame outside complete source")
            predicted[camera, frame].append(
                (pred_index[mapping[camera, track["id"]]], padded_box(point["bbox"], padding))
            )
    values = {
        "gt_ids": [],
        "tracker_ids": [],
        "similarity_scores": [],
        "num_gt_ids": len(ids),
        "num_tracker_ids": len(pred_ids),
        "num_gt_dets": 0,
        "num_tracker_dets": 0,
    }
    per_camera = {}
    for camera in sorted(metadata):
        truth = defaultdict(list)
        for row in annotations[camera]:
            frame, identity, x, y, width, height = row[:6]
            if frame != int(frame) or not 1 <= frame <= metadata[camera]["frame_count"]:
                raise ValueError("Reference frame outside complete source")
            truth[int(frame)].append((gt_index[int(identity)], [x, y, x + width, y + height]))
        begin = len(values["gt_ids"])
        a_count = b_count = 0
        for frame in range(1, metadata[camera]["frame_count"] + 1):
            a, b = truth[frame], predicted[camera, frame]
            values["gt_ids"].append(np.array([identity for identity, _ in a], dtype=int))
            values["tracker_ids"].append(np.array([identity for identity, _ in b], dtype=int))
            values["similarity_scores"].append(
                overlap([box for _, box in a], [box for _, box in b])
            )
            a_count += len(a)
            b_count += len(b)
        values["num_gt_dets"] += a_count
        values["num_tracker_dets"] += b_count
        subset = {
            **values,
            "gt_ids": values["gt_ids"][begin:],
            "tracker_ids": values["tracker_ids"][begin:],
            "similarity_scores": values["similarity_scores"][begin:],
            "num_gt_dets": a_count,
            "num_tracker_dets": b_count,
        }
        metric = trackeval.metrics.Identity({"PRINT_CONFIG": False}).eval_sequence(subset)
        per_camera[camera] = {
            "idf1": float(metric["IDF1"]),
            "annotated_boxes": a_count,
            "predicted_boxes": b_count,
        }
    metric = trackeval.metrics.Identity({"PRINT_CONFIG": False}).eval_sequence(values)
    return {
        "identity": {k: float(metric[k]) for k in ["IDF1", "IDP", "IDR", "IDTP", "IDFP", "IDFN"]},
        "annotated_vehicles": len(ids),
        "annotated_boxes": values["num_gt_dets"],
        "predicted_boxes": values["num_tracker_dets"],
        "camera_frame_slots": len(values["gt_ids"]),
        "per_camera": per_camera,
        "annotation_padding_px_per_edge": padding,
        "eligibility": "Raw-box corner ROI eligibility held fixed; padding changes only IoU matching geometry",
    }
