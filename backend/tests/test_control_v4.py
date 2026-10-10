"""Meaningful batched-controller regression and safety-boundary checks."""

import numpy as np
import pytest
from atlas.control import FeedbackController
from atlas.control_v2 import SafetyGate, SafetyProfile
from atlas.control_v4 import NetworkConfig, NetworkController
from atlas.signal_runtime import selected_profile


def test_batched_matches_frozen_mpc_across_random_lane_states():
    rng = np.random.default_rng(71)
    moves = [[("a", "x"), ("b", "y")], [("c", "z")], [("a", "y"), ("c", "x")]]
    original = FeedbackController(selected_profile(), moves)
    candidate = NetworkController(moves)
    for index in range(100):
        gate = SafetyGate(["GGrr", "rrGG", "GrGr"], SafetyProfile(min_green=10))
        gate.current = index % 3
        gate.started = 0
        t = 12 + index % 49
        lanes = {
            a: {
                "queue": float(rng.integers(0, 8)),
                "vehicles": 8.0,
                "capacity": 30.0,
                "arrival_rate": float(rng.uniform(0, 0.5)),
                "starvation": float(rng.integers(0, 300)),
                "waiting": 0.0,
            }
            for a in ("a", "b", "c", "x", "y", "z")
        }
        original.last_decision = -(10**9)
        candidate.last_decision = -(10**9)
        assert candidate.decide(t, gate, lanes)[0] == original.decide(t, gate, lanes)[0]


def test_minimum_green_current_one_and_sensor_fallback():
    controller = NetworkController([[("a", "b")], [("c", "d")]])
    gate = SafetyGate(["Gr", "rG"], SafetyProfile(min_green=10))
    gate.current = 1
    assert controller.decide(10, gate, {})[0] == 1
    assert controller.decide(11, gate, {})[0] == 1
    assert controller.decide(60, gate, {})[0] in gate.allowed(60)


def test_configuration_rejects_nonfinite_or_unbounded_settings():
    with pytest.raises(ValueError):
        NetworkConfig(service_rate=float("nan"))
    with pytest.raises(ValueError):
        NetworkConfig(horizon=10000)
