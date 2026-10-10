"""Experimental shared-table cooperative Q learning behind the independent safety gate."""

import math
import random

import numpy as np


class SharedQ:
    def __init__(self, table=None, training=False, seed=44):
        self.table = {k: list(map(float, v)) for k, v in (table or {}).items()}
        self.training = training
        self.rng = random.Random(seed)
        self.updates = 0
        self.alpha, self.gamma, self.epsilon = 0.15, 0.95, 0.2

    def values(self, key):
        return (
            self.table.setdefault(key, [0.0, 0.0])
            if self.training
            else self.table.get(key, [0.0, 0.0])
        )

    def update(self, old, action, reward, new, valid):
        if not self.training:
            return
        values = self.values(old)
        target = reward + self.gamma * max(self.values(new)[a] for a in valid)
        values[action] += self.alpha * (target - values[action])
        self.updates += 1


class CooperativeQController:
    """Each junction acts independently, shares policy/reward and actual graph capacity."""

    def __init__(self, movements, learner):
        self.movements = movements
        self.inbound = sorted({a for phase in movements for a, _ in phase})
        self.learner = learner
        self.previous = None
        self.last_explanation = {}

    def decide(self, t, gate, lanes, coordination=None):
        feasible = gate.allowed(t)
        required = {a for phase in self.movements for pair in phase for a in pair}
        if len(feasible) == 1:
            return feasible[0], "independent_safety_single_action"
        if any(
            a not in lanes
            or any(
                not math.isfinite(float(lanes[a].get(k, -1))) or lanes[a].get(k, -1) < 0
                for k in ("queue", "vehicles", "capacity", "arrival_rate")
            )
            or lanes[a]["capacity"] <= 0
            for a in required
        ):
            return feasible[0], "invalid_sensor_safe_fallback"
        pressure = [
            sum(
                lanes[a]["queue"]
                + 0.5 * max(0, lanes[a]["vehicles"] - lanes[a]["queue"])
                - lanes[b]["vehicles"] / lanes[b]["capacity"]
                for a, b in phase
            )
            + 0.2 * (coordination or {}).get(i, 0)
            for i, phase in enumerate(self.movements)
        ]
        alternatives = [i for i in feasible if i != gate.current]
        other = max(alternatives, key=lambda i: (pressure[i], -i)) if alternatives else gate.current
        choices = {0: gate.current, 1: other}
        abstract_valid = [
            a
            for a, phase in choices.items()
            if phase in feasible and (a == 0 or other != gate.current)
        ]
        local_queue = sum(lanes[a]["queue"] for a in self.inbound)
        capacity = sum(lanes[a]["capacity"] for a in self.inbound)
        destination = max(
            (
                lanes[b]["vehicles"] / lanes[b]["capacity"]
                for phase in self.movements
                for _, b in phase
            ),
            default=0,
        )
        global_queue = sum(v["queue"] for v in lanes.values())
        state = ":".join(
            map(
                str,
                (
                    min(3, int(local_queue)),
                    int(pressure[gate.current] >= pressure[other]),
                    min(2, int(destination * 3)),
                    min(3, int((t - gate.started) / 15)),
                    int(local_queue / max(1, capacity) > 0.25),
                ),
            )
        )
        if self.previous is not None:
            old_state, old_action, old_queue, old_time = self.previous
            if t - old_time < 5 and gate.current in feasible:
                return gate.current, "learned_decision_interval"
            reward = (old_queue - global_queue) / max(1, len(lanes)) - 0.01 * global_queue / max(
                1, len(lanes)
            )
            self.learner.update(old_state, old_action, reward, state, abstract_valid)
        known = state in self.learner.table
        if self.learner.training and self.learner.rng.random() < self.learner.epsilon:
            action = self.learner.rng.choice(abstract_valid)
        elif known:
            values = self.learner.values(state)
            action = max(abstract_valid, key=lambda a: (values[a], -a))
        else:
            # Unvisited states retain an explicit deterministic pressure fallback.
            action = max(abstract_valid, key=lambda a: (pressure[choices[a]], -a))
        selected = choices[action]
        self.previous = (state, action, global_queue, t)
        self.last_explanation = {
            "t": t,
            "selected": selected,
            "constraints": feasible,
            "reason": "cooperative_tabular_q" if known else "unvisited_state_pressure_fallback",
            "model_state": state,
            "q_values": self.learner.values(state),
            "shared_reward": "Measured network queue change, including neighboring lanes; modeled outcome only",
            "experimental": True,
            "field_actuation": False,
        }
        return selected, self.last_explanation["reason"]


def surrogate_features(frame):
    """Causal state features for an observed-policy five-second queue surrogate."""
    lanes = list(frame["lane_observations"].values())
    queues = np.asarray([v["queue"] for v in lanes], dtype=float)
    vehicles = np.asarray([v["vehicles"] for v in lanes], dtype=float)
    capacity = np.asarray([v["capacity"] for v in lanes], dtype=float)
    signals = list(frame["signals"].values())
    return [
        float(frame["queue"]),
        float(queues.sum()),
        float(vehicles.sum()),
        float(capacity.sum()),
        float(sum(v["arrival_rate"] for v in lanes)),
        float(np.max(vehicles / np.maximum(capacity, 1), initial=0)),
        float(sum(v["starvation"] for v in lanes) / max(1, len(lanes))),
        float(sum(v["execution"] not in {"hold", "green_started"} for v in signals)),
        float(sum(v["phase"] for v in signals) / max(1, len(signals))),
        float(frame["t"] / 300),
        float(len(lanes)),
        float(len(signals)),
    ]
