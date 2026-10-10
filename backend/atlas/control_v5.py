"""Decision-time controller portfolio; never selects using future episode outcomes."""

import math
from dataclasses import dataclass

from atlas.control_v4 import NetworkConfig, NetworkController
from atlas.evaluation.signal import choose_phase


@dataclass(frozen=True)
class PortfolioConfig:
    congestion_threshold: float = 0.3
    downstream_threshold: float = 0.8
    hysteresis: float = 0.05
    minimum_family_dwell_seconds: int = 30

    def __post_init__(self):
        if not all(
            math.isfinite(v)
            for v in (self.congestion_threshold, self.downstream_threshold, self.hysteresis)
        ):
            raise ValueError("Portfolio thresholds must be finite")
        if (
            not 0 < self.congestion_threshold <= 1
            or not 0 < self.downstream_threshold <= 1
            or not 0 <= self.hysteresis < self.congestion_threshold
            or self.minimum_family_dwell_seconds < 1
        ):
            raise ValueError("Invalid bounded portfolio settings")


class ControllerPortfolio:
    def __init__(self, movements, settings=PortfolioConfig()):
        self.movements, self.settings = movements, settings
        self.inbound = sorted({a for phase in movements for a, _ in phase})
        self.destinations = sorted({b for phase in movements for _, b in phase})
        self.required = set(self.inbound + self.destinations)
        self.cached = NetworkController(movements, NetworkConfig())
        self.family = "cached_mpc"
        self.family_since = 0
        self.since_service = [0] * len(movements)
        self.last_explanation = {}

    def decide(self, t, gate, lanes, coordination=None):
        feasible = gate.allowed(t)
        if any(
            a not in lanes
            or any(
                not math.isfinite(float(lanes[a].get(key, -1))) or lanes[a].get(key, -1) < 0
                for key in ("vehicles", "queue", "capacity", "arrival_rate", "starvation")
            )
            or lanes[a]["capacity"] <= 0
            for a in self.required
        ):
            action = gate.current if gate.current in feasible else feasible[0]
            self.last_explanation = {
                "t": t,
                "selected": action,
                "reason": "missing_or_invalid_sensor_safe_fallback",
                "constraints": feasible,
                "family": "safe_hold",
            }
            return action, self.last_explanation["reason"]
        # Current lane occupancy only. No city identity, route files, seed, demand
        # regime label, final metric or counterfactual winner enters selection.
        capacity = sum(lanes[a]["capacity"] for a in self.inbound)
        occupancy = sum(lanes[a]["vehicles"] for a in self.inbound) / max(1, capacity)
        downstream = max(
            (lanes[b]["vehicles"] / lanes[b]["capacity"] for b in self.destinations), default=0
        )
        threshold = self.settings.congestion_threshold - (
            self.settings.hysteresis if self.family == "max_pressure" else 0
        )
        desired = (
            "max_pressure"
            if occupancy >= threshold or downstream >= self.settings.downstream_threshold
            else "cached_mpc"
        )
        if (
            desired != self.family
            and t - self.family_since >= self.settings.minimum_family_dwell_seconds
        ):
            self.family, self.family_since = desired, t
        self.since_service = [age + 1 for age in self.since_service]
        self.since_service[gate.current] = 0
        if self.family == "cached_mpc":
            action, reason = self.cached.decide(t, gate, lanes, coordination)
        else:
            queues = [
                sum(lanes[a]["queue"] for a in {a for a, _ in phase}) for phase in self.movements
            ]
            pressures = [
                sum(
                    lanes[a]["vehicles"] / lanes[a]["capacity"]
                    - lanes[b]["vehicles"] / lanes[b]["capacity"]
                    for a, b in phase
                )
                for phase in self.movements
            ]
            action = (
                choose_phase(
                    "max_pressure",
                    gate.current,
                    t - gate.started,
                    queues,
                    pressures,
                    [30] * len(self.movements),
                    self.since_service,
                )
                if gate.clearance is None
                else gate.current
            )
            reason = "observed_congestion_pressure_fallback"
        if action not in feasible:
            action = gate.current if gate.current in feasible else feasible[0]
        self.last_explanation = {
            "t": t,
            "selected": action,
            "reason": reason,
            "family": self.family,
            "inbound_occupancy_fraction": occupancy,
            "maximum_downstream_occupancy_fraction": downstream,
            "constraints": feasible,
            "field_actuation": False,
            "forecast_scope": "causal EWMA arrivals only; city ML forecasts not promoted",
        }
        return action, reason
