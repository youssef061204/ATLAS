"""Experimental learned candidates obey safety and frozen inference boundaries."""

from atlas.control_v2 import SafetyGate
from atlas.learned_control_v4 import CooperativeQController, SharedQ


def lanes():
    return {
        name: {"queue": q, "vehicles": q, "capacity": 10, "arrival_rate": 0.1}
        for name, q in (("a", 4), ("b", 0), ("c", 1), ("d", 0))
    }


def test_q_learning_uses_delayed_actual_reward_and_frozen_inference():
    learner = SharedQ(training=True, seed=44)
    controller = CooperativeQController([[("a", "b")], [("c", "d")]], learner)
    gate = SafetyGate(["Gr", "rG"])
    first, _ = controller.decide(12, gate, lanes())
    assert learner.updates == 0
    second, _ = controller.decide(17, gate, lanes())
    assert first in gate.allowed(12) and second in gate.allowed(17)
    assert learner.updates == 1
    frozen = SharedQ(learner.table)
    before = {k: list(v) for k, v in frozen.table.items()}
    other = CooperativeQController(controller.movements, frozen)
    other.decide(20, gate, lanes())
    other.decide(25, gate, lanes())
    assert frozen.table == before
    assert frozen.updates == 0


def test_unsafe_learned_request_cannot_bypass_clearance_or_maximum():
    gate = SafetyGate(["Gr", "rG"])
    controller = CooperativeQController([[("a", "b")], [("c", "d")]], SharedQ())
    for t in range(100):
        request, _ = controller.decide(t, gate, lanes())
        assert request in gate.allowed(t)
        lamp, _ = gate.advance(t, request)
        assert lamp in gate.states or lamp in ("yr", "ry", "rr")
    assert gate.switches >= 1
    assert gate.rejected == 0
