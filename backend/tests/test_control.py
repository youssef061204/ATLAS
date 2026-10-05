"""Signal mapping, feasible actions, causal inputs, pairing and frozen selection."""

from dataclasses import replace

import numpy as np
import pytest
from atlas.control import (
    ControlConfig,
    FeedbackController,
    SignalMachine,
    movement_scores,
    phase_movements,
    queue_cost,
)
from atlas.evaluation.signal_lab import assert_paired, demand_variant
from atlas.evaluation.signal_study import aggregate, paired_stats, protocol


def lanes():
    return {
        "a": {
            "vehicles": 4,
            "queue": 3,
            "capacity": 10,
            "waiting": 120,
            "starvation": 90,
            "arrival_rate": 0.2,
        },
        "b": {
            "vehicles": 1,
            "queue": 0,
            "capacity": 5,
            "waiting": 0,
            "starvation": 0,
            "arrival_rate": 0,
        },
        "c": {
            "vehicles": 10,
            "queue": 8,
            "capacity": 10,
            "waiting": 180,
            "starvation": 30,
            "arrival_rate": 0.1,
        },
        "d": {
            "vehicles": 0,
            "queue": 0,
            "capacity": 5,
            "waiting": 0,
            "starvation": 0,
            "arrival_rate": 0,
        },
    }


def test_phase_mapping_respects_link_indices_and_deduplicates():
    links = [(("a", "b", "i"),), (("c", "d", "j"),), (("a", "b", "i"),)]
    assert phase_movements(["GrG", "rGr"], links) == [[("a", "b")], [("c", "d")]]
    with pytest.raises(ValueError):
        phase_movements(["G"], links)
    with pytest.raises(ValueError):
        phase_movements(["yyy"], links)


def test_pressure_components_and_forecast_units():
    moves = [[("a", "b")], [("c", "d")]]
    config = ControlConfig(
        wait_weight=1, queue_weight=1, starvation_weight=1, forecast_weight=1, switch_penalty=0
    )
    assert movement_scores(moves, lanes(), config)[0] == pytest.approx(
        0.4 - 0.2 + 0.3 + 0.2 + 0.15 + 0.2
    )
    assert movement_scores(moves, lanes(), replace(config, downstream_weight=0))[
        0
    ] == pytest.approx(1.25)
    assert movement_scores(moves, lanes(), replace(config, family="queue"))[0] == pytest.approx(
        0.3 - 0.2 + 0.3 + 0.2 + 0.15 + 0.2
    )


def test_single_stage_objective_and_switch_cost():
    config = ControlConfig(
        queue_weight=0.5, starvation_weight=1, downstream_weight=2, switch_penalty=3
    )
    x = np.array([2.0, 4.0])
    waiting = np.array([180.0, 0.0])
    blocked = np.array([0.0, 0.5])
    assert queue_cost(x, waiting, blocked, False, config) == pytest.approx(13)
    assert (
        queue_cost(x, waiting, blocked, True, config)
        - queue_cost(x, waiting, blocked, False, config)
        == 3
    )


def test_min_green_action_mask_and_invalid_phase():
    signal = SignalMachine(["Gr", "rG"])
    assert signal.mask(9) == [0]
    with pytest.raises(ValueError):
        signal.advance(9, 1)
    with pytest.raises(ValueError):
        signal.advance(10, 2)
    assert signal.advance(10, 1) == ("yr", "switch")


def test_exact_yellow_all_red_and_no_duplicate_switches():
    signal = SignalMachine(["Gr", "rG"])
    states = [signal.advance(t, 1 if t == 10 else signal.current)[0] for t in range(16)]
    assert states[10:] == ["yr", "yr", "yr", "rr", "rr", "rG"]
    assert signal.switches == 1
    assert signal.yellow_seconds == 3 and signal.all_red_seconds == 2
    assert signal.started == 15
    with pytest.raises(ValueError):
        signal.advance(24, 0)


def test_max_green_masks_hold():
    signal = SignalMachine(["Gr", "rG"])
    assert signal.mask(60) == [1]
    with pytest.raises(ValueError):
        signal.advance(60, 0)
    assert signal.advance(60, 1)[1] == "switch"


def test_switch_penalty_and_decision_interval():
    c = FeedbackController(
        ControlConfig(switch_penalty=2, decision_interval=5), [[("a", "b")], [("c", "d")]]
    )
    s = SignalMachine(["Gr", "rG"])
    assert c.decide(12, s, lanes())[0] == 0
    assert c.decide(13, s, lanes())[1] == "decision_interval"
    c2 = FeedbackController(ControlConfig(switch_penalty=0), c.movements)
    assert c2.decide(12, s, lanes())[0] == 1
    assert c.decide(60, s, lanes())[0] == 1


def test_controller_and_actuator_reset_have_no_episode_state():
    first = FeedbackController(ControlConfig(), [[("a", "b")], [("c", "d")]])
    first.decide(12, SignalMachine(["Gr", "rG"]), lanes())
    second = FeedbackController(ControlConfig(), first.movements)
    assert second.last_decision < 0 and np.all(second.last_scores == 0)
    assert SignalMachine(["Gr", "rG"]).switches == 0


def test_starved_lane_has_priority_without_future_inputs():
    data = lanes()
    data["a"]["starvation"] = 190
    c = FeedbackController(ControlConfig(switch_penalty=0), [[("a", "b")], [("c", "d")]])
    assert c.decide(12, SignalMachine(["Gr", "rG"]), data) == (0, "starvation_bound")


def test_mpc_is_feasible_and_deterministic():
    c = FeedbackController(
        ControlConfig(family="mpc", forecast_weight=1), [[("a", "b")], [("c", "d")]]
    )
    s = SignalMachine(["Gr", "rG"])
    assert c.decide(11, s, lanes())[0] == 0
    a = c.decide(12, s, lanes())[0]
    assert a in s.mask(12)
    assert a == FeedbackController(c.config, c.movements).decide(12, s, lanes())[0]
    assert c.decide(60, s, lanes())[0] == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_green": 9},
        {"max_green": 61},
        {"switch_penalty": -1},
        {"forecast_weight": float("nan")},
        {"family": "deep_rl"},
        {"beam_width": 0},
    ],
)
def test_invalid_controller_configuration(kwargs):
    with pytest.raises(ValueError):
        ControlConfig(**kwargs)


def test_demand_perturbations_are_deterministic_and_paired(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text(
        '<routes><vType id="car"/>'
        + "".join(f'<trip id="v{i}" depart="{i}" from="north" to="south"/>' for i in range(50))
        + "</routes>"
    )
    for variant in ["nominal", "low", "peak", "imbalance", "burst"]:
        a = tmp_path / "a.xml"
        b = tmp_path / "b.xml"
        assert demand_variant(source, a, 0, 50, variant, 1001) == demand_variant(
            source, b, 0, 50, variant, 1001
        )
        assert a.read_bytes() == b.read_bytes()


def test_pairing_rejects_seed_route_and_initial_phase_changes():
    keys = [
        "scenario",
        "source",
        "seed",
        "begin",
        "duration",
        "warmup",
        "teleport",
        "variant",
        "sumo",
    ]
    a = {
        "signature": dict.fromkeys(keys, 0),
        "scheduled_demand_sha256": "abc",
        "initial_state": "Gr",
        "states": ["Gr", "rG"],
        "phase_movements": [],
    }
    b = {**a, "signature": dict(a["signature"])}
    assert assert_paired([a, b])
    b["signature"]["seed"] = 1
    with pytest.raises(ValueError):
        assert_paired([a, b])
    b["signature"]["seed"] = 0
    b["initial_state"] = "rG"
    with pytest.raises(ValueError):
        assert_paired([a, b])


def test_split_integrity_and_ten_new_test_seeds():
    p = protocol()
    seen = set()
    for name in ["tuning", "validation", "test", "ablations", "transfer", "stress"]:
        seeds = {x[0] if isinstance(x, (list, tuple)) else x for x in p[name]}
        assert not seen & seeds
        seen |= seeds
    assert len(p["test"]) == 10 and not {42, 43, 44} & set(p["test"])
    assert len(p["candidates"]) == 20


def test_paired_statistics_and_sample_sd():
    results = []
    for seed, a, b in [(1, 10, 20), (2, 12, 22), (3, 14, 24)]:
        for policy, value in [("atlas_improved", a), ("fixed", b)]:
            from atlas.evaluation.signal_study import METRICS

            results.append(
                {
                    "signature": {"seed": seed, "policy": policy},
                    "metrics": dict.fromkeys(METRICS, value),
                }
            )
    score = paired_stats(results, "fixed")
    assert score["paired_delay_reduction_s"] == 10
    assert score["paired_delay_reduction_ci95_s"] == [10, 10]
    assert score["wins"] == 3
    assert aggregate(results)["atlas_improved"]["mean_delay_s"]["std"] == 2


def test_runtime_uses_frozen_profile_and_rejects_stale_source(tmp_path):
    import json

    from atlas import config
    from atlas.signal_runtime import selected_profile

    path = config.ROOT / "docs/signal-controller-frozen.json"
    actual = json.loads(path.read_text(encoding="utf-8"))
    assert selected_profile().family == actual["settings"]["family"]
    assert selected_profile().horizon == actual["settings"]["horizon"]
    actual["controller_sha256"] = "stale"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(actual), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        selected_profile(bad)
