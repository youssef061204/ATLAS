"""Associate an observed turning location with official GIS signal markers."""

from __future__ import annotations

from math import dist

US_SURVEY_FT_TO_M = 1200 / 3937


def classify_turn(
    point_survey_ft: tuple[float, float],
    markers_survey_ft: dict[int, tuple[float, float]],
    max_distance_m: float = 50,
) -> dict[str, float | int | None]:
    if not markers_survey_ft or max_distance_m <= 0:
        raise ValueError("Need official signal markers and a positive proximity gate")
    distances = {
        signal: dist(point_survey_ft, marker) * US_SURVEY_FT_TO_M
        for signal, marker in markers_survey_ft.items()
    }
    closest = min(distances, key=distances.get)
    nearest_m = distances[closest]
    return {
        "nearest_signal": closest,
        "nearest_distance_m": nearest_m,
        "supported_signal": closest if nearest_m <= max_distance_m else None,
    }
