"""Experimental risk-aware network control; historical frozen MPC stays untouched."""

import hashlib
import hmac
import json
import math
import time
from dataclasses import asdict, dataclass

import numpy as np

from atlas.evaluation.signal import choose_phase


@dataclass(frozen=True)
class SafetyProfile:
    min_green: int = 12
    max_green: int = 60
    yellow: int = 3
    all_red: int = 2
    pedestrian_walk: int = 7
    pedestrian_clearance: int = 10
    pedestrian_phases: tuple = ()
    conflict_pairs: tuple = ()
    jurisdiction: str = "research; agency timing survey required"

    def __post_init__(self):
        if (
            self.min_green < 10
            or self.max_green
            < max(self.min_green, self.pedestrian_walk + self.pedestrian_clearance)
            or self.yellow < 3
            or self.all_red < 2
        ):
            raise ValueError("Invalid modeled safety envelope")


class SafetyGate:
    """Actuator owns clearance and masks; optimizers cannot directly set lamps."""

    def __init__(self, states, profile=SafetyProfile()):
        self.profile = profile
        self.states = tuple(states)
        if len(states) < 2 or len({len(s) for s in states}) != 1:
            raise ValueError("Need at least two equal-width legal source green phases")
        if any(not any(c in "Gg" for c in s) or any(c not in "rGgs" for c in s) for s in states):
            raise ValueError("Only source green states may be targets")
        if any(not 0 <= i < len(states) for i in profile.pedestrian_phases):
            raise ValueError("Invalid pedestrian phase")
        for a, b in profile.conflict_pairs:
            if not 0 <= a < len(states[0]) or not 0 <= b < len(states[0]):
                raise ValueError("Invalid conflict movement index")
            # g is permissive/yielding; conflict restriction concerns protected G.
            if any(s[a] == s[b] == "G" for s in states):
                raise ValueError("Conflicting protected movements in source phases")
        self.current = self.target = 0
        self.started = self.last_time = 0
        self.clearance = None
        self.switches = self.rejected = 0

    def minimum(self, phase):
        p = self.profile
        return max(
            p.min_green,
            p.pedestrian_walk + p.pedestrian_clearance if phase in p.pedestrian_phases else 0,
        )

    def allowed(self, t):
        if self.clearance is not None or t - self.started < self.minimum(self.current):
            return [self.current]
        return [
            i
            for i in range(len(self.states))
            if i != self.current or t - self.started < self.profile.max_green
        ]

    def advance(self, t, requested):
        if not math.isfinite(t) or t < self.last_time:
            raise ValueError("Actuation timestamps must be monotonic")
        self.last_time = t
        p = self.profile
        if self.clearance is not None:
            age = t - self.clearance
            if age < p.yellow:
                return self.yellow(), "yellow"
            if age < p.yellow + p.all_red:
                return "r" * len(self.states[0]), "all_red"
            self.current, self.started, self.clearance = self.target, t, None
            return self.states[self.current], "green_started"
        valid = self.allowed(t)
        if type(requested) is not int or requested not in valid:
            self.rejected += 1
            # Deterministic cyclic safe fallback, including max-green expiry.
            requested = (
                self.current
                if self.current in valid
                else min(valid, key=lambda i: (i - self.current) % len(self.states))
            )
            reason = "rejected_unsafe_request"
        else:
            reason = "hold"
        if requested != self.current:
            self.target, self.clearance = requested, t
            self.switches += 1
            return self.yellow(), reason if reason.startswith("rejected") else "switch"
        return self.states[self.current], reason

    def yellow(self):
        return "".join("y" if c in "Gg" else "r" for c in self.states[self.current])


@dataclass(frozen=True)
class RiskConfig:
    horizon: int = 30
    beam_width: int = 4
    risk_weight: float = 0.2
    tail_weight: float = 0.15
    switch_weight: float = 0.5
    spillback_weight: float = 2
    fairness_weight: float = 0.2
    forecast_weight: float = 1
    coordination_weight: float = 0.2
    dynamic_budget: bool = True
    service_rate: float = 0.65
    expansion_budget: int = 240
    small_phase_pressure_fallback: bool = True

    def __post_init__(self):
        if (
            self.horizon not in {20, 30, 40, 60}
            or not 1 <= self.beam_width <= 8
            or self.expansion_budget < 8
        ):
            raise ValueError("Invalid bounded optimizer settings")
        if (
            any(
                not math.isfinite(v) or v < 0
                for k, v in asdict(self).items()
                if k.endswith("weight")
            )
            or self.service_rate <= 0
        ):
            raise ValueError("Objective weights must be nonnegative and finite")


def cvar(values, alpha=0.8):
    """Exact empirical CVaR with fractional mass at the quantile boundary."""
    a = np.sort(np.asarray(values, dtype=float))[::-1]
    if not 0 <= alpha < 1 or len(a) == 0 or not np.all(np.isfinite(a)):
        raise ValueError("Invalid CVaR inputs")
    mass = (1 - alpha) * len(a)
    whole = int(mass)
    numerator = a[:whole].sum()
    if whole < len(a):
        numerator += (mass - whole) * a[whole]
    return float(numerator / mass)


class RiskController:
    def __init__(self, movements, settings=RiskConfig()):
        self.movements, self.settings = movements, settings
        self.inbound = sorted({a for moves in movements for a, _ in moves})
        self.index = {a: i for i, a in enumerate(self.inbound)}
        self.served = np.array(
            [[any(a == lane for a, _ in moves) for lane in self.inbound] for moves in movements],
            dtype=float,
        )
        self.next_time = 0
        self.warm_action = 0
        self.last_explanation = {}
        self.last_service = [0] * len(movements)

    def decide(self, t, gate, lanes, coordination=None):
        tick = time.perf_counter()
        if gate.clearance is None:
            self.last_service[gate.current] = t
        valid = gate.allowed(t)
        if len(valid) == 1:
            action = valid[0]
            self.last_explanation = {
                "t": t,
                "selected": action,
                "reason": "single_feasible_safety_action",
                "constraints": valid,
                "alternatives": [],
            }
            return action, "single_feasible_safety_action"
        if t < self.next_time and gate.current in valid:
            return gate.current, "decision_interval"
        c = self.settings
        required = {lane for moves in self.movements for pair in moves for lane in pair}
        if any(
            a not in lanes
            or any(
                not math.isfinite(float(lanes[a].get(k, float("nan")))) or lanes[a][k] < 0
                for k in ("queue", "vehicles", "capacity", "arrival_rate", "starvation")
            )
            or lanes[a]["capacity"] <= 0
            for a in required
        ):
            action = min(valid, key=lambda i: ((i - gate.current) % len(self.movements), i))
            self.last_explanation = {
                "t": t,
                "selected": action,
                "reason": "invalid_sensor_fallback",
                "alternatives": [],
                "constraints": valid,
            }
            return action, "invalid_sensor_fallback"
        q = np.array(
            [
                lanes[a]["queue"] + 0.5 * max(0, lanes[a]["vehicles"] - lanes[a]["queue"])
                for a in self.inbound
            ]
        )
        caps = np.array([lanes[a]["capacity"] for a in self.inbound])
        ages = np.array([lanes[a]["starvation"] for a in self.inbound])
        rates = np.array([lanes[a]["arrival_rate"] for a in self.inbound]) * c.forecast_weight
        load = float(np.max(q / caps, initial=0))
        horizon = (
            (20 if load < 0.15 else 40 if load > 0.65 else c.horizon)
            if c.dynamic_budget
            else c.horizon
        )
        width = min(c.beam_width, 3 if load < 0.15 else 6) if c.dynamic_budget else c.beam_width
        interval = 3 if load < 0.15 else 1
        self.next_time = t + interval
        downstream = np.array(
            [
                [
                    max(
                        (
                            lanes[b]["vehicles"] / lanes[b]["capacity"]
                            for a, b in moves
                            if a == lane
                        ),
                        default=0,
                    )
                    for lane in self.inbound
                ]
                for moves in self.movements
            ]
        )
        pressures = np.array(
            [
                sum(
                    lanes[a]["vehicles"] / lanes[a]["capacity"]
                    - lanes[b]["vehicles"] / lanes[b]["capacity"]
                    for a, b in moves
                )
                for moves in self.movements
            ]
        )
        if c.small_phase_pressure_fallback and len(self.movements) <= 3:
            phase_queues = [
                sum(lanes[a]["queue"] for a in {a for a, _ in moves}) for moves in self.movements
            ]
            action = choose_phase(
                "max_pressure",
                gate.current,
                t - gate.started,
                phase_queues,
                pressures,
                [30] * len(self.movements),
                [t - last for last in self.last_service],
            )
            self.next_time = t + 1
            self.last_explanation = {
                "t": t,
                "selected": int(action),
                "reason": "small_phase_pressure_fallback",
                "constraints": valid,
                "alternatives": [
                    {"phase": i, "first_stage_cost": float(-value)}
                    for i, value in enumerate(pressures)
                ],
                "uncertainty": "Topology heuristic, not a calibrated OOD detector",
                "decision_ms": (time.perf_counter() - tick) * 1000,
            }
            return int(action), "small_phase_pressure_fallback"
        urgent = [
            i
            for i in valid
            if any(
                lanes[a]["queue"] > 0 and lanes[a]["starvation"] >= 180
                for a, _ in self.movements[i]
            )
        ]
        if urgent:
            action = max(
                urgent,
                key=lambda i: (
                    max(lanes[a]["starvation"] for a, _ in self.movements[i]),
                    pressures[i],
                    -i,
                ),
            )
            self.last_explanation = {
                "t": t,
                "selected": action,
                "reason": "starvation_priority",
                "constraints": valid,
                "alternatives": [],
                "hard_wait_guarantee": False,
            }
            return action, "starvation_priority"
        # Arrival uncertainty is a declared sensitivity envelope, not learned probability.
        scenario_rates = np.array([rates * 0.7, rates, rates * 1.3])
        beam = [(0.0, np.tile(q, (3, 1)), ages, gate.current, gate.current, t - gate.started)]
        alternatives, expansions = {}, 0
        for stage in range(horizon // 10):
            nodes = []
            for cost, queues, waits, phase, first, phase_age in beam:
                choices = (
                    valid
                    if stage == 0
                    else (
                        [phase] if phase_age < gate.minimum(phase) else range(len(self.movements))
                    )
                )
                # Warm start is only a tie-break, never a bypass of feasibility.
                choices = sorted(choices, key=lambda i: (i != self.warm_action, i))
                for action in choices:
                    if phase == action and phase_age >= gate.profile.max_green:
                        continue
                    if expansions >= c.expansion_budget:
                        break
                    expansions += 1
                    switched = phase != action
                    green = 10 - (gate.profile.yellow + gate.profile.all_red if switched else 0)
                    service = (
                        c.service_rate * self.served[action] * np.clip(1 - downstream[action], 0, 1)
                    )
                    updated = np.maximum(0, queues + scenario_rates * 10 - service * green)
                    mid = (queues + updated) / 2
                    scenario_cost = np.sum(mid, axis=1)
                    risk = cvar(scenario_cost)
                    new_waits = np.where(service > 0, 0, waits + 10)
                    penalty = float(
                        scenario_cost.mean()
                        + c.risk_weight * risk
                        + c.tail_weight * np.max(mid)
                        + c.spillback_weight * np.sum(mid.mean(axis=0) * downstream[action])
                        + c.fairness_weight * np.sum(new_waits / 180 * mid.mean(axis=0))
                        + c.switch_weight * switched
                    )
                    hint = (coordination or {}).get(action, 0)
                    penalty -= c.coordination_weight * max(-5, min(5, hint))
                    value = cost + 10 * penalty
                    chosen_first = action if stage == 0 else first
                    if stage == 0:
                        alternatives[action] = value
                    nodes.append(
                        (
                            value,
                            updated,
                            new_waits,
                            action,
                            chosen_first,
                            green if switched else phase_age + 10,
                        )
                    )
            if not nodes:
                break
            beam = sorted(nodes, key=lambda n: (n[0], n[4]))[:width]
        action = (
            int(beam[0][4])
            if beam and beam[0][4] in valid
            else max(valid, key=lambda i: (pressures[i], -i))
        )
        self.warm_action = action
        self.last_explanation = {
            "t": t,
            "selected": action,
            "reason": "risk_aware_fluid_search",
            "horizon_s": horizon,
            "decision_interval_s": interval,
            "beam_width": width,
            "expansions": expansions,
            "objective": float(beam[0][0]),
            "expected_outcome": "Fluid queue objective; not an empirically calibrated delay reduction",
            "arrival_uncertainty": [0.7, 1, 1.3],
            "risk_model": "Empirical CVaR of three assumed equally weighted arrival envelopes",
            "alternatives": [
                {"phase": i, "first_stage_cost": float(value)}
                for i, value in sorted(alternatives.items())
            ],
            "constraints": valid,
            "binding_constraint": "max_green" if gate.current not in valid else None,
            "downstream_max_density": float(downstream.max()),
            "decision_ms": (time.perf_counter() - tick) * 1000,
        }
        return action, "risk_aware_fluid_search"


class NetworkCoordinator:
    """One-hop graph messages using observed destination-lane capacity/demand."""

    def hints(self, controllers, lanes):
        lane_owners = {a: signal for signal, c in controllers.items() for a in c.inbound}
        messages = {}
        for signal, controller in controllers.items():
            scores = {}
            for i, moves in enumerate(controller.movements):
                scores[i] = sum(
                    (lanes[a]["arrival_rate"] - lanes[b]["queue"] / lanes[b]["capacity"])
                    for a, b in moves
                    if lane_owners.get(b) and lane_owners[b] != signal
                )
            messages[signal] = scores
        return messages


def authorize_priority(payload, signature, secret, now_s, consumed):
    """Authorized simulation request only. Cameras cannot create signed requests."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if not secret or not hmac.compare_digest(
        hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest(), signature
    ):
        raise ValueError("Unauthorized priority request")
    if (
        payload.get("kind") not in {"emergency", "transit"}
        or payload.get("expires", 0) < now_s
        or payload.get("issued", now_s + 1) > now_s
        or not payload.get("nonce")
        or payload["nonce"] in consumed
    ):
        raise ValueError("Expired, future, replayed or invalid priority request")
    consumed.add(payload["nonce"])
    return payload
