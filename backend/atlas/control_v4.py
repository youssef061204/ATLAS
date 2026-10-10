"""Cached, batched fluid MPC research candidate; no automatic promotion.

Observations are causal. The independent SafetyGate remains sole lamp owner.
Unlike v2, the number of green phases never selects a different algorithm.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NetworkConfig:
    horizon: int = 30
    beam_width: int = 6
    min_green: int = 12
    service_rate: float = 0.65
    queue_weight: float = 0.15
    downstream_weight: float = 1.0
    fairness_weight: float = 0.25
    switch_weight: float = 0.5
    coordination_weight: float = 0.0
    decision_interval: int = 1
    running_weight: float = 0.5
    arrival_weight: float = 1.0
    adaptive_queue: bool = False

    def __post_init__(self):
        if self.horizon not in {20, 30, 40, 60} or not 1 <= self.beam_width <= 12:
            raise ValueError("Invalid bounded search")
        if not 10 <= self.min_green <= 60 or not 1 <= self.decision_interval <= 5:
            raise ValueError("Invalid timing settings")
        values = [
            self.service_rate,
            self.queue_weight,
            self.downstream_weight,
            self.fairness_weight,
            self.switch_weight,
            self.coordination_weight,
            self.running_weight,
            self.arrival_weight,
        ]
        if any(not math.isfinite(v) or v < 0 for v in values) or self.service_rate == 0:
            raise ValueError("Objective settings must be finite and nonnegative")


class NetworkController:
    """Precompute topology and batch every beam stage's feasible expansions."""

    def __init__(self, movements, settings=NetworkConfig()):
        self.movements, self.settings = movements, settings
        self.inbound = sorted({a for moves in movements for a, _ in moves})
        self.served = np.array(
            [[any(a == lane for a, _ in moves) for lane in self.inbound] for moves in movements],
            dtype=bool,
        )
        self.destinations = [
            [tuple(b for a, b in moves if a == lane) for lane in self.inbound]
            for moves in movements
        ]
        self.required = {lane for moves in movements for pair in moves for lane in pair}
        self.last_decision = -(10**9)
        self.last_explanation = {}

    def decide(self, t, gate, lanes, coordination=None):
        c = self.settings
        valid = gate.allowed(t)
        elapsed = t - gate.started
        if len(valid) == 1 or (elapsed < c.min_green and gate.current in valid):
            return self._record(
                t,
                gate.current if gate.current in valid else valid[0],
                "minimum_or_clearance",
                valid,
            )
        if t - self.last_decision < c.decision_interval and gate.current in valid:
            return self._record(t, gate.current, "decision_interval", valid)
        if any(
            a not in lanes
            or any(
                not math.isfinite(float(lanes[a].get(k, -1))) or lanes[a].get(k, -1) < 0
                for k in ("queue", "vehicles", "capacity", "arrival_rate", "starvation")
            )
            or lanes[a]["capacity"] <= 0
            for a in self.required
        ):
            return self._record(t, valid[0], "invalid_sensor_fallback", valid)
        self.last_decision = t
        q = np.array(
            [
                lanes[a]["queue"]
                + c.running_weight * max(0, lanes[a]["vehicles"] - lanes[a]["queue"])
                for a in self.inbound
            ],
            dtype=float,
        )
        rates = np.array([lanes[a]["arrival_rate"] for a in self.inbound]) * c.arrival_weight
        ages = np.array([lanes[a]["starvation"] for a in self.inbound], dtype=float)
        blocked = np.array(
            [
                [
                    max((lanes[b]["vehicles"] / lanes[b]["capacity"] for b in dest), default=0)
                    for dest in phase
                ]
                for phase in self.destinations
            ]
        )
        if not c.downstream_weight:
            blocked[:] = 0
        urgent = [
            i
            for i in valid
            if any(
                lanes[a]["queue"] and lanes[a]["starvation"] >= 180 for a, _ in self.movements[i]
            )
        ]
        if urgent:

            def priority(i):
                age = max(lanes[a]["starvation"] for a, _ in self.movements[i] if lanes[a]["queue"])
                density = sum(
                    lanes[a]["vehicles"] / lanes[a]["capacity"]
                    + c.queue_weight * lanes[a]["queue"] / lanes[a]["capacity"]
                    + c.fairness_weight
                    * min(lanes[a]["starvation"], 180)
                    / 180
                    * lanes[a]["queue"]
                    / lanes[a]["capacity"]
                    + c.arrival_weight * 10 * lanes[a]["arrival_rate"] / lanes[a]["capacity"]
                    - c.downstream_weight * lanes[b]["vehicles"] / lanes[b]["capacity"]
                    for a, b in self.movements[i]
                )
                return age, density

            action = max(urgent, key=priority)
            return self._record(t, action, "starvation_priority", valid)
        queue_weight = c.queue_weight
        if c.adaptive_queue:
            # Smooth state-dependent tail cost; no city identity or future routes.
            queue_weight += 0.85 * min(1.0, float(np.max(q)) / 6.0) ** 2
        service = c.service_rate * self.served * np.clip(1 - blocked, 0, 1)
        costs, queues, waits = np.zeros(1), q[None, :], ages[None, :]
        phases, firsts, phase_ages = (
            np.array([gate.current]),
            np.array([gate.current]),
            np.array([elapsed]),
        )
        alternatives, expansions = {}, 0
        hints = np.array([(coordination or {}).get(i, 0) for i in range(len(self.movements))])
        for stage in range(c.horizon // 10):
            parent, actions = [], []
            for row, (phase, age) in enumerate(zip(phases, phase_ages, strict=True)):
                choices = (
                    valid
                    if stage == 0
                    else ([int(phase)] if age < c.min_green else range(len(self.movements)))
                )
                for action in choices:
                    if action == phase and age >= gate.profile.max_green:
                        continue
                    parent.append(row)
                    actions.append(action)
            if not parent:
                break
            parent, actions = np.array(parent), np.array(actions)
            switched = actions != phases[parent]
            green = 10 - 5 * switched
            updated = np.maximum(0, queues[parent] + rates * 10 - service[actions] * green[:, None])
            next_waits = np.where(
                self.served[actions] & (service[actions] > 0), 0, waits[parent] + 10
            )
            mid = (queues[parent] + updated) / 2
            penalty = (
                mid.sum(axis=1)
                + queue_weight * mid.max(axis=1)
                + c.fairness_weight * (next_waits * (mid > 0)).sum(axis=1) / 180
                + c.downstream_weight * (blocked[actions] * mid).sum(axis=1)
                + c.switch_weight * switched
                - c.coordination_weight * np.clip(hints[actions], -5, 5)
            )
            values = costs[parent] + 10 * penalty
            chosen = actions if stage == 0 else firsts[parent]
            if stage == 0:
                alternatives = {int(a): float(v) for a, v in zip(actions, values, strict=True)}
            expansions += len(actions)
            # Stable ordering preserves original MPC ties in neutral configuration.
            keep = np.argsort(values, kind="stable")[: c.beam_width]
            costs, queues, waits = values[keep], updated[keep], next_waits[keep]
            phases, firsts = actions[keep], chosen[keep]
            phase_ages = np.where(switched, green, phase_ages[parent] + 10)[keep]
        action = int(firsts[0]) if len(firsts) and firsts[0] in valid else valid[0]
        self.last_explanation = {
            "t": t,
            "selected": action,
            "reason": "cached_network_fluid_search",
            "constraints": valid,
            "expansions": expansions,
            "fluid_objective": float(costs[0]),
            "horizon_s": c.horizon,
            "alternatives": [{"phase": a, "first_stage_cost": v} for a, v in alternatives.items()],
            "forecast_provenance": "causal simulated lane-arrival EWMA; not field calibrated",
            "network_messages": c.coordination_weight != 0,
        }
        return action, "cached_network_fluid_search"

    def _record(self, t, action, reason, valid):
        self.last_explanation = {"t": t, "selected": action, "reason": reason, "constraints": valid}
        return action, reason
