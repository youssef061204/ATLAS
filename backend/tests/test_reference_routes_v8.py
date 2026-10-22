from __future__ import annotations

from atlas.reference_routes_v8 import destination


def test_oracle_route_requires_completed_corrobated_side_exit() -> None:
    assert destination(1, 80, 200, "N_in") == "E_out"
    assert destination(3, -90, 200, "S_in") == "W_out"
    assert destination(1, 20, 200, "N_in") is None
    assert destination(3, -90, 299.5, "S_in") is None
    assert destination(1, 80, 200, "N_out") is None
