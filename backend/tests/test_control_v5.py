import pytest
from atlas.control_v2 import SafetyGate, SafetyProfile
from atlas.control_v5 import ControllerPortfolio, PortfolioConfig


def inputs(vehicles=0):
    return {
        a: {
            "vehicles": vehicles,
            "queue": vehicles,
            "capacity": 10,
            "arrival_rate": 0.2,
            "starvation": 0,
        }
        for a in ("n", "s", "out")
    }


def test_portfolio_uses_present_occupancy_and_preserves_independent_safety():
    gate = SafetyGate(["Gr", "rG"], SafetyProfile())
    policy = ControllerPortfolio([[("n", "out")], [("s", "out")]])
    low = inputs()
    assert policy.decide(15, gate, low)[0] in gate.allowed(15)
    assert policy.family == "cached_mpc"
    high = inputs(8)
    high["out"]["vehicles"] = 0
    policy.decide(35, gate, high)
    assert policy.family == "max_pressure"
    assert "inbound_occupancy_fraction" in policy.last_explanation
    policy.decide(40, gate, low)
    assert policy.family == "max_pressure"  # family dwell prevents oscillation
    policy.decide(70, gate, low)
    assert policy.family == "cached_mpc"


def test_invalid_sensor_hold_respects_mask_at_maximum_green():
    gate = SafetyGate(["Gr", "rG"], SafetyProfile())
    policy = ControllerPortfolio([[("n", "out")], [("s", "out")]])
    assert policy.decide(70, gate, {})[0] in gate.allowed(70)
    assert policy.last_explanation["family"] == "safe_hold"
    with pytest.raises(ValueError):
        PortfolioConfig(congestion_threshold=float("nan"))
