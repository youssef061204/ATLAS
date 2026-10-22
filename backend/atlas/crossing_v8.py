"""Interpolate independently annotated passage through an estimated cross-section."""


def observed_crossing(a, b, local_y_ft=1045.0):
    """Return crossing time for a through vehicle, or None if the pair is ineligible.

    The local-y section is the ATLAS 7 modeled junction, not a surveyed stop line.
    Each input is a mapping with t, local_x/y, direction, movement and lane_id.
    """
    if (
        a["direction"] != b["direction"]
        or a["direction"] not in (2, 4)
        or a["movement"] != 1
        or b["movement"] != 1
        or a["lane_id"] not in (1, 2, 3, 4)
        or b["lane_id"] not in (1, 2, 3, 4)
        or abs(a["local_x"]) >= 70
        or abs(b["local_x"]) >= 70
        or not 0 < b["t"] - a["t"] <= 0.2
    ):
        return None
    north = a["direction"] == 2
    crossed = (
        a["local_y"] < local_y_ft <= b["local_y"]
        if north
        else a["local_y"] > local_y_ft >= b["local_y"]
    )
    if not crossed:
        return None
    fraction = (local_y_ft - a["local_y"]) / (b["local_y"] - a["local_y"])
    return a["t"] + fraction * (b["t"] - a["t"])
