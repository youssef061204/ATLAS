"""Post-hoc annotation coverage audit for CityFlow research evaluations.

The official multi-camera labels omit many visible single-camera vehicles. This
audit measures which predicted observations can be checked against those labels;
it never removes predictions or changes the frozen primary IDF1 denominator.
"""

from collections import Counter, defaultdict

from scipy.optimize import linear_sum_assignment

from atlas.multicamera_metrics_v7 import overlap, padded_box


def audit_annotation_evidence(tracks, rois, metadata, annotations, links, padding=10):
    """Return aggregate evidence only, without source boxes or reference IDs."""
    predicted = defaultdict(list)
    for track in tracks:
        camera = track["camera"]
        roi = rois[camera]
        key = (camera, track["id"])
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
                raise ValueError("Prediction outside complete source video")
            predicted[camera, frame].append((key, padded_box(point["bbox"], padding)))

    evidence = defaultdict(Counter)
    reference_cameras = defaultdict(set)
    per_camera = {}
    for camera in sorted(metadata):
        truth = defaultdict(list)
        for row in annotations[camera]:
            frame, identity, x, y, width, height = row[:6]
            if frame != int(frame) or not 1 <= frame <= metadata[camera]["frame_count"]:
                raise ValueError("Reference outside complete source video")
            truth[int(frame)].append((int(identity), [x, y, x + width, y + height]))
            reference_cameras[int(identity)].add(camera)
        counts = Counter()
        for frame in range(1, metadata[camera]["frame_count"] + 1):
            gt, pred = truth[frame], predicted[camera, frame]
            counts["annotated_boxes"] += len(gt)
            counts["predicted_boxes"] += len(pred)
            if gt:
                counts["frames_with_annotations"] += 1
                counts["predicted_boxes_in_annotated_frames"] += len(pred)
            else:
                counts["predicted_boxes_in_unannotated_frames"] += len(pred)
            if not gt or not pred:
                continue
            similarity = overlap([box for _, box in gt], [box for _, box in pred])
            gt_idx, pred_idx = linear_sum_assignment(similarity, maximize=True)
            for i, j in zip(gt_idx, pred_idx, strict=True):
                if similarity[i, j] >= 0.5:
                    counts["matched_annotated_boxes"] += 1
                    evidence[pred[j][0]][gt[i][0]] += 1
        counts["source_frames"] = metadata[camera]["frame_count"]
        per_camera[camera] = dict(counts)

    def resolved(key):
        counts = evidence.get(key)
        if not counts:
            return None
        identity, support = counts.most_common(1)[0]
        if support < 3 or support / counts.total() < 0.8:
            return None
        return identity

    resolved_by_key = {
        (track["camera"], track["id"]): resolved((track["camera"], track["id"])) for track in tracks
    }
    cameras_with_resolved_track = defaultdict(set)
    for (camera, _), identity in resolved_by_key.items():
        if identity is not None:
            cameras_with_resolved_track[identity].add(camera)
    link_status = {scope: Counter() for scope in ("all", "cross_camera", "same_camera")}
    link_kinds = Counter()
    linked_reference_vehicles = set()
    for link in links:
        left_key, right_key = tuple(link["left"]), tuple(link["right"])
        left = resolved_by_key.get(left_key)
        right = resolved_by_key.get(right_key)
        cross_camera = left_key[0] != right_key[0]
        scope = "cross_camera" if cross_camera else "same_camera"
        link_kinds[link.get("kind", "unknown")] += 1
        if left is None or right is None:
            status = "not_checkable_from_labels"
        elif left == right:
            status = "same_annotated_vehicle"
            if cross_camera:
                linked_reference_vehicles.add(left)
        else:
            status = "different_annotated_vehicles"
        link_status["all"][status] += 1
        link_status[scope][status] += 1

    totals = {
        key: sum(row.get(key, 0) for row in per_camera.values())
        for key in (
            "annotated_boxes",
            "predicted_boxes",
            "frames_with_annotations",
            "predicted_boxes_in_annotated_frames",
            "predicted_boxes_in_unannotated_frames",
            "matched_annotated_boxes",
            "source_frames",
        )
    }
    totals["annotated_box_match_fraction"] = (
        totals["matched_annotated_boxes"] / totals["annotated_boxes"]
        if totals["annotated_boxes"]
        else None
    )
    totals["prediction_annotation_match_fraction"] = (
        totals["matched_annotated_boxes"] / totals["predicted_boxes"]
        if totals["predicted_boxes"]
        else None
    )
    totals["annotated_vehicles"] = len(reference_cameras)
    totals["annotated_multicamera_vehicles"] = sum(
        len(cameras) > 1 for cameras in reference_cameras.values()
    )
    totals["predicted_tracklets_with_any_label_match"] = len(evidence)
    totals["predicted_tracklets_with_resolved_label"] = sum(
        identity is not None for identity in resolved_by_key.values()
    )
    totals["annotated_vehicles_with_resolved_tracks_in_multiple_cameras"] = sum(
        len(cameras) > 1 for cameras in cameras_with_resolved_track.values()
    )
    totals["annotated_vehicles_with_verified_cross_camera_links"] = len(linked_reference_vehicles)
    for bucket in link_status.values():
        for key in (
            "same_annotated_vehicle",
            "different_annotated_vehicles",
            "not_checkable_from_labels",
        ):
            bucket.setdefault(key, 0)
    if sum(link_status["all"].values()) != len(links):
        raise AssertionError("Link accounting mismatch")
    return {
        "totals": totals,
        "per_camera": per_camera,
        "accepted_link_audit": {scope: dict(bucket) for scope, bucket in link_status.items()},
        "accepted_link_kinds": dict(link_kinds),
    }
