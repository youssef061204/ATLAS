"""Conservative geometric association from calibrated, synchronized video tracks.

Association uses no reference identities. Uncertain, static-only and ambiguous
matches are rejected rather than merged by appearance similarity alone.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class GeoTracklet:
    camera: str
    identity: int
    times: np.ndarray
    xy_m: np.ndarray


def pair_evidence(a, b, median_gate_m=3.0, tail_gate_m=5.0):
    if a.camera == b.camera or len(a.times) < 3 or len(b.times) < 3:
        return None
    start = max(a.times[0], b.times[0])
    end = min(a.times[-1], b.times[-1])
    if end - start < 0.8:
        return None
    times = np.arange(start, end + 0.001, 0.2)
    points = []
    for track in [a, b]:
        nearest = np.searchsorted(track.times, times)
        nearest = np.clip(nearest, 1, len(track.times) - 1)
        gaps = track.times[nearest] - track.times[nearest - 1]
        valid = gaps <= 0.31
        xy = np.column_stack(
            [np.interp(times, track.times, track.xy_m[:, axis]) for axis in [0, 1]]
        )
        points.append((xy, valid))
    valid = points[0][1] & points[1][1]
    if valid.sum() < 5:
        return None
    first, second = points[0][0][valid], points[1][0][valid]
    distances = np.linalg.norm(first - second, axis=1)
    median, p90 = float(np.median(distances)), float(np.percentile(distances, 90))
    if median > median_gate_m or p90 > tail_gate_m:
        return None
    motion = [np.linalg.norm(p[-1] - p[0]) for p in [first, second]]
    if min(motion) < 2:
        return None
    va, vb = first[-1] - first[0], second[-1] - second[0]
    cosine = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))
    if cosine < 0.5:
        return None
    return {
        "median_distance_m": median,
        "p90_distance_m": p90,
        "synchronized_samples": int(valid.sum()),
        "overlap_s": float(end - start),
        "motion_cosine": cosine,
        "cost": median + 0.2 * p90,
    }


def associate_geometry(tracks, ambiguity_margin_m=0.75):
    keys = [(t.camera, t.identity) for t in tracks]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate camera-track identity")
    candidates = []
    neighbors = {i: [] for i in range(len(tracks))}
    for i, a in enumerate(tracks):
        if len(a.times) and (
            not np.isfinite(a.times).all()
            or not np.isfinite(a.xy_m).all()
            or np.any(np.diff(a.times) <= 0)
        ):
            raise ValueError("Invalid calibrated track or source times")
        for j in range(i + 1, len(tracks)):
            b = tracks[j]
            evidence = pair_evidence(a, b)
            if evidence is None:
                continue
            candidates.append((evidence["cost"], i, j, evidence))
            neighbors[i].append((evidence["cost"], j))
            neighbors[j].append((evidence["cost"], i))
    parent = list(range(len(tracks)))
    cameras = [{t.camera} for t in tracks]

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    accepted = []
    ambiguous = 0
    for cost, i, j, evidence in sorted(candidates):
        # Alternatives are evaluated for the SAME opposing camera, rather than
        # treating valid observations from a third camera as competing identities.
        rivals = [c for c, k in neighbors[i] if k != j and tracks[k].camera == tracks[j].camera]
        rivals += [c for c, k in neighbors[j] if k != i and tracks[k].camera == tracks[i].camera]
        if rivals and min(rivals) - cost < ambiguity_margin_m:
            ambiguous += 1
            continue
        left, right = find(i), find(j)
        if left == right or cameras[left] & cameras[right]:
            continue
        parent[right] = left
        cameras[left] |= cameras[right]
        accepted.append({"left": list(keys[i]), "right": list(keys[j]), **evidence})
    components = {}
    mapping = {}
    for i, key in enumerate(keys):
        root = find(i)
        components.setdefault(root, len(components) + 1)
        mapping[key] = components[root]
    return (
        mapping,
        accepted,
        {"candidate_links": len(candidates), "ambiguous_rejections": ambiguous},
    )
