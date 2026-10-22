"""Account for each reference state along an observed-CV-to-native lifecycle.

This is a diagnostic of a completed run, not an estimator for online control.
Reference identities are used only after CV demand and SUMO output are fixed.
"""

from collections import Counter, defaultdict
from math import dist

import numpy as np
from scipy.optimize import linear_sum_assignment


def spatial_cv_matches(reference_rows, cv_rows, gate_m=4.0):
    """Return one-to-one same-second spatial links; these are not ID labels."""
    if not reference_rows or not cv_rows:
        return {}
    actual = np.asarray([row["point"] for row in reference_rows], dtype=float)
    predicted = np.asarray([row["point"] for row in cv_rows], dtype=float)
    distances = np.linalg.norm(actual[:, None] - predicted[None, :], axis=2)
    left, right = linear_sum_assignment(np.where(distances <= gate_m, distances, 1e9))
    return {
        str(reference_rows[i]["id"]): str(cv_rows[j]["id"])
        for i, j in zip(left, right, strict=True)
        if distances[i, j] <= gate_m
    }


def audit_lifecycle(reference, cv, entries, birth_mapping, native, start, end, gate_m=4.0):
    """Partition every 1 Hz reference state into a mutually exclusive stage.

    ``reference`` uses decisecond keys; ``cv`` and ``native`` use integer-second
    keys. The completed run's birth mapping is diagnostic and may be uncertain.
    A reference state remains in the denominator even if no stage can represent
    it. Native first/last times are observed FCD samples, not exact depart/exit.
    """
    if not (0 <= start < end):
        raise ValueError("Invalid half-open evaluation window")
    requested = {str(row["id"]): row for row in entries}
    native_by_id = defaultdict(dict)
    for t, rows in native.items():
        for row in rows:
            identity = str(row["id"])
            if t in native_by_id[identity]:
                raise ValueError(f"Duplicate native state: {identity} at {t}")
            native_by_id[identity][t] = row
    native_ranges = {
        identity: (min(states), max(states)) for identity, states in native_by_id.items()
    }
    categories = Counter()
    cv_matches_by_stage = Counter()
    cv_identity_by_stage = Counter()
    lifecycle = {}
    matching_distances = []

    for t in range(start, end):
        actual = reference.get(t * 10, [])
        cv_links = spatial_cv_matches(actual, cv.get(t, []), gate_m)
        native_frame = {str(row["id"]): row for row in native.get(t, [])}
        for row in actual:
            identity = str(row["id"])
            match = birth_mapping.get(identity)
            cv_id = cv_links.get(identity)
            record = lifecycle.setdefault(
                identity,
                {
                    "reference_id": identity,
                    "first_reference_s": t,
                    "last_reference_s": t,
                    "reference_states": 0,
                    "same_second_cv_matches": 0,
                    "matched_cv_ids": set(),
                    "stage_counts": Counter(),
                    "video_frame_first": t * 10,
                    "video_frame_last": t * 10,
                },
            )
            record["last_reference_s"] = t
            record["video_frame_last"] = t * 10
            record["reference_states"] += 1
            if cv_id is not None:
                record["same_second_cv_matches"] += 1
                record["matched_cv_ids"].add(cv_id)

            if match is None:
                stage = "no_birth_association"
            else:
                native_id = str(match["native_id"])
                birth_s = float(match["birth_s"])
                if t < birth_s:
                    stage = "before_cv_birth"
                elif native_id not in native_ranges:
                    stage = "requested_never_sampled_native"
                elif t < native_ranges[native_id][0]:
                    stage = "before_first_native_sample"
                elif t > native_ranges[native_id][1]:
                    stage = "after_last_native_sample"
                elif native_id not in native_frame:
                    stage = "native_sample_gap"
                else:
                    error_m = dist(row["point"], native_frame[native_id]["point"])
                    matching_distances.append(error_m)
                    stage = "native_within_4m" if error_m <= gate_m else "native_beyond_4m"
            categories[stage] += 1
            cv_matches_by_stage[(stage, cv_id is not None)] += 1
            consistency = (
                "absent"
                if cv_id is None
                else "same_birth_id"
                if match is not None and str(match["native_id"]) == f"cv_{cv_id}"
                else "other_cv_id"
            )
            cv_identity_by_stage[(stage, consistency)] += 1
            record["stage_counts"][stage] += 1

    for identity, record in lifecycle.items():
        match = birth_mapping.get(identity)
        if match is not None:
            native_id = str(match["native_id"])
            entry = requested.get(native_id)
            record["birth_association"] = {
                "cv_id": native_id,
                "requested_birth_s": match["birth_s"],
                "association_distance_m": match["birth_association_distance_m"],
                "requested_edge": entry.get("edge") if entry else None,
                "requested_lane": entry.get("lane") if entry else None,
                "native_first_sample_s": native_ranges.get(native_id, (None, None))[0],
                "native_last_sample_s": native_ranges.get(native_id, (None, None))[1],
            }
        else:
            record["birth_association"] = None
        record["matched_cv_ids"] = sorted(record["matched_cv_ids"])
        record["stage_counts"] = dict(sorted(record["stage_counts"].items()))

    states = sum(categories.values())
    paired = categories["native_within_4m"] + categories["native_beyond_4m"]
    return {
        "reference_states": states,
        "reference_vehicles": len(lifecycle),
        "requested_births": len(requested),
        "native_sampled_vehicle_ids": len(native_ranges),
        "requested_births_sampled_in_native_fcd": len(requested.keys() & native_ranges.keys()),
        "associated_reference_vehicle_ids": sum(
            row["birth_association"] is not None for row in lifecycle.values()
        ),
        "same_second_cv_matched_reference_states": sum(
            row["same_second_cv_matches"] for row in lifecycle.values()
        ),
        "stage_counts": dict(sorted(categories.items())),
        "same_second_cv_match_by_stage": {
            stage: {
                "matched": cv_matches_by_stage[(stage, True)],
                "unmatched": cv_matches_by_stage[(stage, False)],
            }
            for stage in sorted(categories)
        },
        "same_second_cv_identity_by_stage": {
            stage: {
                category: cv_identity_by_stage[(stage, category)]
                for category in ("same_birth_id", "other_cv_id", "absent")
            }
            for stage in sorted(categories)
        },
        "native_presence_coverage": paired / states if states else None,
        "within_4m_reference_coverage": categories["native_within_4m"] / states if states else None,
        "conditional_native_position_mae_m": float(np.mean(matching_distances))
        if matching_distances
        else None,
        "per_vehicle": [lifecycle[key] for key in sorted(lifecycle, key=lambda x: (len(x), x))],
    }
