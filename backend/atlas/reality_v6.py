"""Observed traffic import and independent physical-evaluation primitives.

FHWA NGSIM coordinates and kinematics use feet (US survey feet for the global
State Plane coordinates). Local lengths/speeds use the documented foot units.
Source annotations remain independent of ATLAS perception and SUMO output.
"""

import math
from collections import defaultdict

FOOT_M = 0.3048
SURVEY_FOOT_M = 1200 / 3937


def normalize_ngsim(row):
    required = (
        "vehicle_id",
        "frame_id",
        "global_time",
        "local_x",
        "local_y",
        "v_vel",
        "v_length",
        "lane_id",
        "direction",
        "section_id",
        "int_id",
    )
    if any(row.get(k) in (None, "") for k in required):
        raise ValueError("NGSIM observation lacks identity, time, coordinates or lane context")
    values = {k: float(row[k]) for k in required if k != "vehicle_id"}
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("Nonfinite observed traffic state")
    integer_fields = ("frame_id", "global_time", "lane_id", "direction", "section_id", "int_id")
    if any(not values[k].is_integer() for k in integer_fields):
        raise ValueError("Fractional source identity, time or lane context")
    if (
        values["global_time"] <= 0
        or values["frame_id"] < 1
        or values["v_vel"] < 0
        or values["v_length"] <= 0
    ):
        raise ValueError("Invalid observation timestamp, frame, speed or length")
    if (
        values["direction"] not in (1, 2, 3, 4)
        or min(values[k] for k in ("lane_id", "section_id", "int_id")) < 0
    ):
        raise ValueError("Invalid direction or road context")
    sequence = int(values["global_time"] - (values["frame_id"] - 1) * 100)
    return {
        "vehicle_id": f"{sequence}:{row['vehicle_id']}",
        "source_vehicle_id": str(row["vehicle_id"]),
        "sequence_epoch_ms": sequence,
        "timestamp_ms": int(values["global_time"]),
        "x_m": values["local_x"] * FOOT_M,
        "y_m": values["local_y"] * FOOT_M,
        "speed_mps": values["v_vel"] * FOOT_M,
        "lane_id": int(values["lane_id"]),
        "direction": int(values["direction"]),
        "section_id": int(values["section_id"]),
        "intersection_id": int(values["int_id"]),
        "length_m": values["v_length"] * FOOT_M,
        "source": "FHWA NGSIM independent video-transcribed annotation",
    }


def partition_tracks(rows, windows):
    """Whole tracks within disjoint chronological windows; crossing tracks excluded."""
    bounds = sorted(windows.items(), key=lambda item: item[1][0])
    if any(a >= b for _, (a, b) in bounds) or any(
        bounds[i][1][1] > bounds[i + 1][1][0] for i in range(len(bounds) - 1)
    ):
        raise ValueError("Overlapping or empty observational partitions")
    tracks = defaultdict(list)
    seen = set()
    for row in rows:
        key = row["vehicle_id"], row["timestamp_ms"]
        if key in seen:
            raise ValueError("Duplicate vehicle/time observation")
        seen.add(key)
        tracks[row["vehicle_id"]].append(row)
    result = {name: [] for name in windows}
    excluded = []
    for identity, track in tracks.items():
        times = [r["timestamp_ms"] for r in track]
        for name, (start, end) in bounds:
            if start <= min(times) and max(times) < end:
                result[name].extend(track)
                break
        else:
            excluded.append(identity)
    return result, excluded


def matched_errors(observed, predicted):
    """No missing predictions converted to zero and no unequal-pair truncation."""
    if len(observed) != len(predicted):
        raise ValueError("Measurements must be explicitly paired")
    errors = []
    for actual, estimate in zip(observed, predicted, strict=True):
        if actual is None or estimate is None:
            continue
        if not math.isfinite(actual) or not math.isfinite(estimate):
            raise ValueError("Nonfinite metric input")
        errors.append(estimate - actual)
    return {
        "pairs": len(errors),
        "eligible_observations": len(observed),
        "coverage": len(errors) / len(observed) if observed else None,
        "mae": sum(abs(e) for e in errors) / len(errors) if errors else None,
        "rmse": math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None,
        "bias": sum(errors) / len(errors) if errors else None,
    }
