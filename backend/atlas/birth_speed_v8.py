"""Opt-in CV birth speed policy for native traffic replay.

The v7 adapter additionally limits a CV-measured birth speed by its distance
to the end of its current edge. An edge may continue through a junction, so
that quantity is not a stopping distance. This policy asks SUMO to insert at
the observed track speed, bounded by the unchanged vehicle type maximum.
SUMO remains responsible for insertion, signals and collision avoidance.
"""

import math


def observed_cv_depart_speed(requested_cv_speed_mps: float, *, max_speed_mps: float) -> float:
    """Return a validated observed CV birth speed without the edge-end clamp."""
    speed = float(requested_cv_speed_mps)
    maximum = float(max_speed_mps)
    if not math.isfinite(speed) or not 0 <= speed <= 25:
        raise ValueError("CV speed must be finite and within the existing 0–25 m/s gate")
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("Vehicle type maximum speed must be finite and positive")
    return min(speed, maximum)
