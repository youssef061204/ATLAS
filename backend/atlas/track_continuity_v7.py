"""Conservative calibrated tracklet handoff with explicit offline gap provenance.

No reference observations enter association. Ambiguous joins remain fragmented.
Gap boxes are separately marked inferred; they are never detector observations.
"""

from collections import defaultdict, deque

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment


def center(obj, matrix):
    x1, y1, x2, y2 = obj["bbox"]
    return cv2.perspectiveTransform(np.float64([[[(x1 + x2) / 2, (y1 + y2) / 2]]]), matrix)[0, 0]


def stitch(frames, matrix, max_gap_s=1.0, ambiguity_margin_m=0.65):
    """Join only absent IDs with unique position/velocity/size-consistent candidates."""
    aliases, states, joins = {}, {}, []
    result = []
    next_id = 1
    for frame in frames:
        time = frame["index"] / 10
        objects = [dict(obj, source_track_id=obj["id"], inferred=False) for obj in frame["objects"]]
        occupied = {}
        # A previously lost source ID can reappear alongside its proposed
        # successor. Preserve both detections and split the contradicted join.
        for index, obj in enumerate(objects):
            raw = obj["id"]
            if raw not in aliases:
                continue
            canonical = aliases[raw]
            if canonical in occupied:
                earlier = occupied[canonical]
                prior = states[canonical]
                predicted = prior["point"] + prior["velocity"] * (time - prior["t"])
                costs = [
                    np.linalg.norm(center(objects[i], matrix) - predicted) for i in [earlier, index]
                ]
                loser = earlier if costs[0] > costs[1] else index
                aliases[objects[loser]["id"]] = next_id
                joins.append(
                    {
                        "kind": "contradiction_split",
                        "time_s": time,
                        "source_track_id": objects[loser]["id"],
                        "old_canonical_id": canonical,
                        "canonical_id": next_id,
                    }
                )
                next_id += 1
                occupied[canonical] = index if loser == earlier else earlier
            else:
                occupied[canonical] = index
        active = {aliases[obj["id"]] for obj in objects if obj["id"] in aliases}
        new = [i for i, obj in enumerate(objects) if obj["id"] not in aliases]
        lost = [
            identity
            for identity, state in states.items()
            if identity not in active and 0 < time - state["t"] <= max_gap_s
        ]
        costs = np.full((len(new), len(lost)), 1e6)
        for i, index in enumerate(new):
            obj = objects[index]
            point = center(obj, matrix)
            area = max(1, (obj["bbox"][2] - obj["bbox"][0]) * (obj["bbox"][3] - obj["bbox"][1]))
            for j, identity in enumerate(lost):
                state = states[identity]
                dt = time - state["t"]
                if obj["class"] != state["class"] or not 0.5 <= area / state["area"] <= 2:
                    continue
                predicted = state["point"] + state["velocity"] * dt
                distance = float(np.linalg.norm(point - predicted))
                # Cap the gate at 3 m; uncertainty grows with a missing interval.
                if distance <= min(3, 1 + 2 * dt):
                    costs[i, j] = distance
        if len(new) and len(lost):
            ii, jj = linear_sum_assignment(costs)
            for i, j in zip(ii, jj, strict=True):
                cost = costs[i, j]
                alternatives = np.concatenate([np.delete(costs[i], j), np.delete(costs[:, j], i)])
                if cost >= 1e6 or (
                    len(alternatives) and alternatives.min() - cost < ambiguity_margin_m
                ):
                    continue
                obj = objects[new[i]]
                identity = lost[j]
                aliases[obj["id"]] = identity
                joins.append(
                    {
                        "kind": "handoff",
                        "time_s": time,
                        "source_track_id": obj["id"],
                        "canonical_id": identity,
                        "gap_s": time - states[identity]["t"],
                        "prediction_residual_m": float(cost),
                    }
                )
        for obj in objects:
            raw = obj["id"]
            if raw not in aliases:
                aliases[raw] = next_id
                next_id += 1
            identity = aliases[raw]
            point = center(obj, matrix)
            prior = states.get(identity)
            history = prior["history"] if prior and time - prior["t"] <= max_gap_s else deque()
            history.append((time, point))
            while history and history[0][0] < time - 0.75:
                history.popleft()
            velocity = np.zeros(2)
            if len(history) >= 3:
                times = np.array([r[0] for r in history])
                points = np.array([r[1] for r in history])
                centered = times - times.mean()
                velocity = centered @ (points - points.mean(axis=0)) / (centered @ centered)
                if np.linalg.norm(velocity) > 30:
                    velocity = np.zeros(2)
            states[identity] = {
                "t": time,
                "point": point,
                "velocity": velocity,
                "history": history,
                "area": max(
                    1, (obj["bbox"][2] - obj["bbox"][0]) * (obj["bbox"][3] - obj["bbox"][1])
                ),
                "class": obj["class"],
            }
            obj["id"] = identity
        if len({o["id"] for o in objects}) != len(objects):
            raise ValueError("Association must never assign two current detections to one identity")
        result.append({**frame, "objects": objects})
    return result, joins


def interpolate_short_gaps(frames, max_missing_s=0.5):
    """Offline bounded linear gaps; preserve raw observations and label inferred boxes."""
    observations = defaultdict(list)
    lookup = {frame["index"]: frame for frame in frames}
    for frame in frames:
        for obj in frame["objects"]:
            observations[obj["id"]].append((frame["index"], obj))
    inserted = 0
    for track in observations.values():
        for (a, first), (b, last) in zip(track[:-1], track[1:], strict=True):
            missing = b - a - 1
            if not 1 <= missing <= round(max_missing_s * 10):
                continue
            for index in range(a + 1, b):
                if index not in lookup:
                    continue
                fraction = (index - a) / (b - a)
                box = (
                    np.array(first["bbox"]) * (1 - fraction) + np.array(last["bbox"]) * fraction
                ).tolist()
                lookup[index]["objects"].append(
                    {
                        **first,
                        "bbox": box,
                        "confidence": min(first["confidence"], last["confidence"]) * 0.75,
                        "inferred": True,
                        "interpolation_span_s": (b - a) / 10,
                        "uncertainty": "Unquantified linear interpolation; not an actual detector observation",
                    }
                )
                inserted += 1
    return frames, inserted
