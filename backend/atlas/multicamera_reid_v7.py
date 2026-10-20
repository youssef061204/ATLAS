"""Research-only geometry/time/appearance association, without reference identities.

Color descriptors are weak appearance evidence, not a trained vehicle-ReID model.
All image descriptors and calibrated trajectories stay local under data terms.
"""

import numpy as np

from atlas.multicamera_v7 import pair_evidence


def velocity(track, last):
    select = track.times >= track.times[-1] - 1 if last else track.times <= track.times[0] + 1
    t, xy = track.times[select], track.xy_m[select]
    if len(t) < 3:
        return None
    t = t - t.mean()
    return t @ (xy - xy.mean(axis=0)) / (t @ t)


def handoff_evidence(a, b, cosine, appearance_gate=0.9, max_gap_s=20):
    if not len(a.times) or not len(b.times):
        return None
    if a.times[0] > b.times[0]:
        a, b = b, a
    gap = float(b.times[0] - a.times[-1])
    same_camera = a.camera == b.camera
    if not 0 <= gap <= (1 if same_camera else max_gap_s) or cosine < appearance_gate:
        return None
    va, vb = velocity(a, True), velocity(b, False)
    if va is None or vb is None or min(np.linalg.norm(va), np.linalg.norm(vb)) < 1:
        return None
    motion = float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))
    if motion < 0.5 or max(np.linalg.norm(va), np.linalg.norm(vb)) > 25:
        return None
    distance = float(np.linalg.norm(a.xy_m[-1] + va * gap / 2 - (b.xy_m[0] - vb * gap / 2)))
    if distance > 5 + 0.2 * gap or np.linalg.norm(b.xy_m[0] - a.xy_m[-1]) > 10 + 22 * gap:
        return None
    return {
        "kind": "same_camera_fragment" if same_camera else "time_geometry_appearance_handoff",
        "gap_s": gap,
        "midpoint_prediction_distance_m": distance,
        "appearance_cosine": cosine,
        "motion_cosine": motion,
        "cost": distance + 10 * (1 - cosine) + gap * 0.05,
    }


def associate(tracks, features, appearance_gate=0.9, ambiguity_margin=0.75, max_gap_s=20):
    keys = [(t.camera, t.identity) for t in tracks]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate track identity")
    for t in tracks:
        if (
            not np.isfinite(t.times).all()
            or not np.isfinite(t.xy_m).all()
            or np.any(np.diff(t.times) <= 0)
        ):
            raise ValueError("Invalid source time or calibrated positions")
    candidates, neighbors = [], {i: [] for i in range(len(tracks))}
    for i, a in enumerate(tracks):
        for j in range(i + 1, len(tracks)):
            b = tracks[j]
            feature_a, feature_b = features.get(keys[i]), features.get(keys[j])
            cosine = (
                float(feature_a @ feature_b)
                if feature_a is not None and feature_b is not None
                else -1
            )
            evidence = pair_evidence(a, b)
            if evidence is not None:
                evidence = {
                    **evidence,
                    "kind": "synchronized_geometric_overlap",
                    "appearance_cosine": cosine,
                }
            else:
                evidence = handoff_evidence(a, b, cosine, appearance_gate, max_gap_s)
            if evidence is not None:
                candidates.append((evidence["cost"], i, j, evidence))
                neighbors[i].append((evidence["cost"], j))
                neighbors[j].append((evidence["cost"], i))
    parent = list(range(len(tracks)))
    members = [{i} for i in range(len(tracks))]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    accepted, rejected_ambiguous, rejected_conflict = [], 0, 0
    for cost, i, j, evidence in sorted(candidates):
        rivals = [c for c, k in neighbors[i] if k != j and tracks[k].camera == tracks[j].camera]
        rivals += [c for c, k in neighbors[j] if k != i and tracks[k].camera == tracks[i].camera]
        if rivals and min(rivals) - cost < ambiguity_margin:
            rejected_ambiguous += 1
            continue
        left, right = find(i), find(j)
        if left == right:
            continue
        conflict = any(
            tracks[a].camera == tracks[b].camera
            and min(tracks[a].times[-1], tracks[b].times[-1])
            - max(tracks[a].times[0], tracks[b].times[0])
            > 0.1
            for a in members[left]
            for b in members[right]
            if len(tracks[a].times) and len(tracks[b].times)
        )
        if conflict:
            rejected_conflict += 1
            continue
        parent[right] = left
        members[left] |= members[right]
        accepted.append({"left": list(keys[i]), "right": list(keys[j]), **evidence})
    components, mapping = {}, {}
    for i, key in enumerate(keys):
        root = find(i)
        components.setdefault(root, len(components) + 1)
        mapping[key] = components[root]
    return (
        mapping,
        accepted,
        {
            "candidate_links": len(candidates),
            "ambiguous_rejections": rejected_ambiguous,
            "overlapping_identity_conflicts": rejected_conflict,
        },
    )
