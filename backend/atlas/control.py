"""Topology-aware feedback policies and a shared protected signal state machine.

No policy sees future routes. Forecasts are causal EWMA lane arrivals; tuning lives
in the experiment protocol, outside the runtime controller.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ControlConfig:
    family: str = "pressure"
    min_green: int = 12
    max_green: int = 60
    decision_interval: int = 1
    switch_penalty: float = 1.0
    wait_weight: float = 0.0
    starvation_weight: float = 0.0
    queue_weight: float = 0.0
    downstream_weight: float = 1.0
    forecast_weight: float = 0.0
    forecast_seconds: int = 10
    horizon: int = 30
    beam_width: int = 4
    service_rate: float = 0.5
    starvation_limit: int = 180

    def __post_init__(self):
        if not 10 <= self.min_green <= self.max_green <= 60:
            raise ValueError("Green times outside common 10–60 second safety envelope")
        if self.family not in {"pressure", "mpc", "queue"}:
            raise ValueError("Unknown controller family")
        if self.decision_interval < 1 or self.horizon < 10 or self.beam_width < 1:
            raise ValueError("Invalid planning configuration")
        weights = [
            self.switch_penalty,
            self.wait_weight,
            self.starvation_weight,
            self.queue_weight,
            self.downstream_weight,
            self.forecast_weight,
        ]
        if any(not np.isfinite(w) or w < 0 for w in weights):
            raise ValueError("Weights must be finite and nonnegative")


def phase_movements(states, links):
    if not states or any(len(state) != len(links) for state in states):
        raise ValueError("Signal/link-index mismatch")
    if any(
        not any(c in "Gg" for c in state) or any(c not in "rGgs" for c in state) for state in states
    ):
        raise ValueError("Use only legal source green phases")
    return [
        sorted(
            {
                (link[0], link[1])
                for i, group in enumerate(links)
                if state[i] in "Gg"
                for link in group
            }
        )
        for state in states
    ]


class SignalMachine:
    """Common actuator: 10 s floor, 60 s ceiling, 3 s yellow, 2 s all-red.

    Policies may conservatively hold above the floor. Historical fixed 10 s and
    max-pressure 12 s decisions remain unchanged; neither baseline is weakened.
    """

    def __init__(self, states):
        self.states = tuple(states)
        self.current = self.target = self.started = 0
        self.clearance = None
        self.switches = self.yellow_seconds = self.all_red_seconds = 0

    def mask(self, t):
        if self.clearance is not None or t - self.started < 10:
            return [self.current]
        return [i for i in range(len(self.states)) if i != self.current or t - self.started < 60]

    def advance(self, t, requested):
        if not 0 <= requested < len(self.states):
            raise ValueError("Invalid phase index")
        reason = "hold"
        if self.clearance is not None:
            age = t - self.clearance
            if age < 3:
                self.yellow_seconds += 1
                return self.yellow(), "yellow"
            if age < 5:
                self.all_red_seconds += 1
                return "r" * len(self.states[0]), "all_red"
            self.current, self.started, self.clearance = self.target, t, None
            return self.states[self.current], "green_started"
        if requested not in self.mask(t):
            raise ValueError("Masked/unsafe phase request")
        if requested != self.current:
            self.target, self.clearance = requested, t
            self.switches += 1
            self.yellow_seconds += 1
            return self.yellow(), "switch"
        return self.states[self.current], reason

    def yellow(self):
        return "".join("y" if c in "Gg" else "r" for c in self.states[self.current])


def movement_scores(movements, lanes, config):
    """Density pressure plus interpretable, consistently normalized observations."""
    scores = []
    for moves in movements:
        score = 0.0
        for upstream, downstream in moves:
            a, b = lanes[upstream], lanes[downstream]
            upstream_value = a["queue"] if config.family == "queue" else a["vehicles"]
            value = upstream_value / a["capacity"]
            value += config.queue_weight * a["queue"] / a["capacity"]
            value += config.wait_weight * a["waiting"] / (60 * a["capacity"])
            value += (
                config.starvation_weight
                * min(a["starvation"], 180)
                / 180
                * a["queue"]
                / a["capacity"]
            )
            value += (
                config.forecast_weight * config.forecast_seconds * a["arrival_rate"] / a["capacity"]
            )
            value -= config.downstream_weight * b["vehicles"] / b["capacity"]
            score += value
        scores.append(score)
    return np.asarray(scores)


def queue_cost(queues, waiting, blocked, switched, config):
    """Single-stage cost; accumulated once per prediction stage, never twice."""
    return float(
        np.sum(queues)
        + config.queue_weight * np.max(queues, initial=0)
        + config.starvation_weight * np.sum(waiting * (queues > 0)) / 180
        + config.downstream_weight * np.sum(blocked * queues)
        + config.switch_penalty * float(switched)
    )


class FeedbackController:
    def __init__(self, config, movements):
        self.config, self.movements = config, movements
        self.last_decision = -(10**9)
        self.last_scores = np.zeros(len(movements))

    def decide(self, t, machine, lanes):
        c = self.config
        current, elapsed = machine.current, t - machine.started
        scores = movement_scores(self.movements, lanes, c)
        self.last_scores = scores
        if machine.clearance is not None or elapsed < c.min_green:
            return current, "clearance_or_minimum_green"
        if elapsed < c.max_green and t - self.last_decision < c.decision_interval:
            return current, "decision_interval"
        self.last_decision = t
        valid = [i for i in range(len(scores)) if i != current or elapsed < c.max_green]
        starved = [
            (i, max((lanes[a]["starvation"] for a, _ in moves if lanes[a]["queue"] > 0), default=0))
            for i, moves in enumerate(self.movements)
            if i in valid
        ]
        urgent = [(i, age) for i, age in starved if age >= c.starvation_limit]
        if urgent:
            return max(urgent, key=lambda item: (item[1], scores[item[0]]))[0], "starvation_bound"
        if c.family == "mpc":
            return self.plan(machine, lanes, valid, elapsed), "receding_horizon"
        penalized = scores.copy()
        penalized[[i for i in range(len(scores)) if i != current]] -= c.switch_penalty
        return max(
            valid, key=lambda i: (penalized[i], i == current)
        ), "max_green" if elapsed >= c.max_green else "pressure_advantage"

    def plan(self, machine, lanes, valid, elapsed):
        """Beam-search fluid queues; only the first feasible action is executed.

        Starts with observed halted/running traffic, uses observed arrival EWMA,
        subtracts feasible service, and charges every switch its five lost seconds.
        No SUMO clones, future demand, or expensive inference are used.
        """
        c = self.config
        inbound = sorted({a for moves in self.movements for a, _ in moves})
        served = [
            np.array([any(a == lane for a, _ in moves) for lane in inbound])
            for moves in self.movements
        ]
        blocked = [
            np.array(
                [
                    max(
                        (
                            lanes[b]["vehicles"] / lanes[b]["capacity"]
                            for a, b in moves
                            if a == lane
                        ),
                        default=0,
                    )
                    for lane in inbound
                ]
            )
            for moves in self.movements
        ]
        q = np.array(
            [
                lanes[a]["queue"] + 0.5 * max(0, lanes[a]["vehicles"] - lanes[a]["queue"])
                for a in inbound
            ]
        )
        if c.downstream_weight == 0:
            blocked = [np.zeros_like(v) for v in blocked]
        rate = np.array([lanes[a]["arrival_rate"] * c.forecast_weight for a in inbound])
        ages = np.array([lanes[a]["starvation"] for a in inbound], dtype=float)
        # Node = cumulative cost, queues, starvation, phase, first action, phase age.
        beam = [(0.0, q, ages, machine.current, machine.current, elapsed)]
        dt = 10
        for stage in range(max(1, c.horizon // dt)):
            next_beam = []
            for cost, queues, waits, phase, first, phase_age in beam:
                options = (
                    valid
                    if stage == 0
                    else ([phase] if phase_age < c.min_green else range(len(served)))
                )
                for action in options:
                    switched = action != phase
                    if not switched and phase_age >= c.max_green:
                        continue
                    capacity = c.service_rate * served[action] * np.clip(1 - blocked[action], 0, 1)
                    green = dt - (5 if switched else 0)
                    updated = np.maximum(0, queues + rate * dt - capacity * green)
                    next_waits = np.where(served[action] & (capacity > 0), 0, waits + dt)
                    penalty = (
                        queue_cost((queues + updated) / 2, next_waits, blocked[action], switched, c)
                        * dt
                    )
                    next_beam.append(
                        (
                            cost + penalty,
                            updated,
                            next_waits,
                            action,
                            action if stage == 0 else first,
                            green if switched else phase_age + dt,
                        )
                    )
            beam = sorted(next_beam, key=lambda node: node[0])[: c.beam_width]
        if not beam:
            return valid[0]
        return int(beam[0][4])
