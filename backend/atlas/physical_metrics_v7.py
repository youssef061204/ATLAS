"""Birth-associated physical prediction errors without a favorable distance censor.

Reference identities resolve evaluation correspondence after simulation. They
never enter demand generation or simulated state updates. Full denominators,
unmatched admissions and errors outside the 4 m gate remain explicit.
"""

from collections import defaultdict

import numpy as np


def birth_correspondence(entries, reference, gate_m=4, ambiguity_m=0.65):
    used, mapping, diagnostics = set(), {}, defaultdict(int)
    for entry in sorted(entries, key=lambda e: (e["t"], e["id"])):
        rows = reference.get(round(entry["t"] * 10), [])
        point = np.asarray(entry["observed_world_m"])
        candidates = sorted(
            (float(np.linalg.norm(point - np.asarray(r["point"]))), str(r["id"])) for r in rows
        )
        if not candidates or candidates[0][0] > gate_m:
            diagnostics["no_reference_within_birth_gate"] += 1
            continue
        if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < ambiguity_m:
            diagnostics["ambiguous_birth_identity"] += 1
            continue
        distance, identity = candidates[0]
        if identity in used:
            diagnostics["duplicate_admissions_for_reference_identity"] += 1
            continue
        used.add(identity)
        mapping[identity] = {
            "native_id": entry["id"],
            "birth_s": entry["t"],
            "birth_association_distance_m": distance,
        }
    return mapping, dict(diagnostics)


def physical_errors(mapping, reference, native, start, end):
    positions, speeds, bins = [], [], defaultdict(list)
    eligible = present = inside_gate = 0
    intervals = [(0, 1), (1, 3), (3, 5), (5, 10), (10, 30), (30, float("inf"))]
    for t in range(start, end):
        predicted = {str(r["id"]): r for r in native.get(t, [])}
        for actual in reference.get(t * 10, []):
            eligible += 1
            match = mapping.get(str(actual["id"]))
            if not match or match["native_id"] not in predicted or t < match["birth_s"]:
                continue
            estimate = predicted[match["native_id"]]
            distance = float(
                np.linalg.norm(np.asarray(actual["point"]) - np.asarray(estimate["point"]))
            )
            present += 1
            inside_gate += distance <= 4
            positions.append(distance)
            if actual.get("speed") is not None and estimate.get("speed") is not None:
                speeds.append(abs(actual["speed"] - estimate["speed"]))
            horizon = t - match["birth_s"]
            for low, high in intervals:
                if low <= horizon < high:
                    bins[low, high].append(distance)
                    break

    def summary(values):
        return {
            "pairs": len(values),
            "mae": float(np.mean(values)) if values else None,
            "p95": float(np.percentile(values, 95)) if values else None,
            "max": max(values) if values else None,
        }

    return {
        "reference_observations": eligible,
        "paired_native_observations": present,
        "native_presence_coverage": present / eligible if eligible else None,
        "within_4m_reference_observations": inside_gate,
        "within_4m_reference_coverage": inside_gate / eligible if eligible else None,
        "uncapped_position_m": summary(positions),
        "matched_speed_mps": summary(speeds),
        "position_by_time_since_birth": [
            {
                "lower_s": low,
                "upper_s": high if np.isfinite(high) else None,
                **summary(bins[low, high]),
            }
            for low, high in intervals
        ],
        "scope": "One unambiguous spatial identity association at observed birth, then free-running native predictions. Position errors are NOT censored at the association gate. Missing native states remain missing; all eligible reference states stay in coverage denominators. Early initialization bins are separate from later prediction errors.",
    }


def acceptance(measured, limits):
    fields = [
        ("count_normalized_mae", "count_normalized_mae_max", False),
        (
            "directional_flow_normalized_absolute_error",
            "directional_flow_normalized_absolute_error_max",
            False,
        ),
        ("queue_count_mae_vehicles", "queue_count_mae_max_vehicles", False),
        ("uncapped_position_mae_m", "matched_position_mae_max_m", False),
        ("within_4m_reference_coverage", "matched_reference_coverage_min", True),
        ("speed_mae_mps", "matched_speed_mae_max_mps", False),
        (
            "travel_time_distribution_wasserstein_s",
            "travel_time_distribution_wasserstein_max_s",
            False,
        ),
    ]
    checks = {}
    for metric, threshold, minimum in fields:
        value = measured.get(metric)
        passed = (
            value is not None
            and np.isfinite(value)
            and (value >= limits[threshold] if minimum else value <= limits[threshold])
        )
        checks[metric] = {
            "value": value,
            "limit": limits[threshold],
            "passed": bool(passed),
            "missing": value is None,
        }
    checks["signal_state_independently_verified"] = {
        "value": measured.get("signal_state_independently_verified"),
        "passed": measured.get("signal_state_independently_verified") is True,
    }
    return {
        "accepted": all(row["passed"] for row in checks.values()),
        "checks": checks,
        "scope": "All preregistered criteria must pass; missing independent observations prevent acceptance. No controller or field-benefit claim follows from a failed gate.",
    }
