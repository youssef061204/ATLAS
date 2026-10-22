"""Decompose free-running vehicle displacement into along-road and cross-road error.

This is a post-outcome diagnostic. The source heading and identity are used only
to score an already completed SUMO run, never to update the simulation.
"""

from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree


def signed_components(reference, simulated, north_tangent, direction):
    """Return signed forward and signed rightward displacement in metres."""
    tangent = np.asarray(north_tangent, dtype=float)
    norm = np.linalg.norm(tangent)
    if norm <= 0 or direction not in (2, 4):
        raise ValueError("Need a northbound road tangent and north/south direction")
    forward = tangent / norm * (1 if direction == 2 else -1)
    right = np.array([forward[1], -forward[0]])
    displacement = np.asarray(simulated, dtype=float) - np.asarray(reference, dtype=float)
    return float(displacement @ forward), float(displacement @ right)


def _summary(values):
    if not values:
        return {"pairs": 0, "mean_m": None, "median_m": None, "p90_absolute_m": None}
    data = np.asarray(values)
    return {
        "pairs": len(values),
        "mean_m": float(np.mean(data)),
        "median_m": float(np.median(data)),
        "p90_absolute_m": float(np.percentile(np.abs(data), 90)),
    }


def residual_audit(mapping, reference, native, directions, road, start, end):
    """Score matched states on the unchanged reference denominator."""
    if not 0 <= start < end:
        raise ValueError("Invalid evaluation window")
    grid = np.linspace(960, 1410, 1801)
    center = road(grid)
    tangent = np.gradient(center, axis=0)
    tree = cKDTree(center)
    groups = defaultdict(lambda: {"longitudinal": [], "lateral": [], "radial": []})
    total = 0
    for second in range(start, end):
        native_at_second = {str(row["id"]): row for row in native.get(second, [])}
        for observed in reference.get(second * 10, []):
            total += 1
            identity = str(observed["id"])
            match = mapping.get(identity)
            if not match or second < match["birth_s"]:
                continue
            predicted = native_at_second.get(str(match["native_id"]))
            if predicted is None:
                continue
            direction = directions[(second, identity)]
            _, nearest = tree.query(observed["point"])
            along, across = signed_components(
                observed["point"], predicted["point"], tangent[nearest], direction
            )
            age = second - match["birth_s"]
            age_bin = (
                "0-1s"
                if age < 1
                else "1-3s"
                if age < 3
                else "3-5s"
                if age < 5
                else "5-10s"
                if age < 10
                else "10s+"
            )
            for key in ("all", f"direction_{direction}", f"age_{age_bin}"):
                groups[key]["longitudinal"].append(along)
                groups[key]["lateral"].append(across)
                groups[key]["radial"].append(float(np.hypot(along, across)))
    return {
        "reference_states": total,
        "paired_native_states": len(groups["all"]["radial"]),
        "groups": {
            key: {dimension: _summary(values) for dimension, values in rows.items()}
            for key, rows in sorted(groups.items())
        },
        "units": "metres; positive longitudinal means SUMO ahead of the observed vehicle; lateral is rightward relative to observed travel direction",
        "limitation": "Curved-road tangent is fitted on 0-300 s. Results are conditional on one birth identity association and native presence; read beside unconditional coverage.",
    }
