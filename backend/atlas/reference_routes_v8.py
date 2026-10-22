"""Conservative completed-exit labels for oracle route diagnostics only."""


def destination(direction: int, x_ft: float, last_s: float, inbound: str) -> str | None:
    """Accept only completed, geometrically corroborated side exits."""
    if last_s >= 299 or inbound not in {"N_in", "S_in"}:
        return None
    if direction == 1 and x_ft > 50:
        return "E_out"
    if direction == 3 and x_ft < -70:
        return "W_out"
    return None
