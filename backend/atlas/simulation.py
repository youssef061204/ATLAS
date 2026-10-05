"""Seeded single-lane intersection with car following and protected two-phase signals."""

from dataclasses import dataclass

import numpy as np

from .schemas import SimulationConfig

DIRECTIONS = ["N", "E", "S", "W"]
DT = 0.5
STOP_LINE = -10.0
EXIT = 80.0
FREE_SPEED = 12.0
LENGTH = 4.5
GAP = 2.5


@dataclass
class Vehicle:
    id: int
    approach: int
    arrival: float
    position: float = -80
    velocity: float = 0
    delay: float = 0
    stops: int = 0
    was_stopped: bool = False


def arrivals(settings: SimulationConfig):
    rng = np.random.default_rng(settings.seed)
    output = []
    for approach, rate in enumerate(settings.demand):
        if rate == 0:
            continue
        t = float(rng.exponential(1 / rate))
        while t < settings.duration:
            output.append((t, approach))
            t += float(rng.exponential(1 / rate))
    output.sort()
    pedestrian_arrivals = []
    for crossing in range(2):
        if settings.pedestrian_rate == 0:
            continue
        t = float(rng.exponential(1 / settings.pedestrian_rate))
        while t < settings.duration:
            pedestrian_arrivals.append((t, crossing))
            t += float(rng.exponential(1 / settings.pedestrian_rate))
    return output, sorted(pedestrian_arrivals)


def simulate(settings: SimulationConfig, policy: str, greens=None, record=True):
    schedule, pedestrian_schedule = arrivals(settings)
    vehicles = []
    complete = []
    pending = [[], [], [], []]
    ped_pending = [[], []]
    pedestrian_waits = []
    phase, phase_started, clearance = 0, 0.0, False
    clearance_start = 0.0
    cursor, ped_cursor = 0, 0
    max_queue = 0
    frames = []
    fixed = greens or [30, 30]
    for step in range(int(settings.duration / DT) + 1):
        t = step * DT
        while cursor < len(schedule) and schedule[cursor][0] <= t:
            arrival, approach = schedule[cursor]
            pending[approach].append(Vehicle(cursor + 1, approach, arrival))
            cursor += 1
        while ped_cursor < len(pedestrian_schedule) and pedestrian_schedule[ped_cursor][0] <= t:
            arrival, crossing = pedestrian_schedule[ped_cursor]
            ped_pending[crossing].append(arrival)
            ped_cursor += 1
        for approach in range(4):
            lane = [v for v in vehicles if v.approach == approach]
            if pending[approach] and (
                not lane or min(v.position for v in lane) > -80 + LENGTH + GAP
            ):
                entering = pending[approach].pop(0)
                entering.delay += max(0, t - entering.arrival)
                vehicles.append(entering)
        queues = [
            sum(v.approach == i and v.velocity < 0.5 and v.position < STOP_LINE for v in vehicles)
            + len(pending[i])
            for i in range(4)
        ]
        green_elapsed = t - phase_started
        if clearance:
            if t - clearance_start >= settings.yellow + settings.all_red:
                phase = 1 - phase
                phase_started = t
                clearance = False
        else:
            current_q = queues[phase] + queues[phase + 2]
            other_q = queues[1 - phase] + queues[3 - phase]
            if policy == "adaptive":
                should_switch = green_elapsed >= settings.max_green or (
                    green_elapsed >= max(settings.min_green, settings.pedestrian_interval)
                    and (other_q > current_q + 2 or current_q == 0 and other_q > 0)
                )
            else:
                should_switch = green_elapsed >= fixed[phase]
            if should_switch:
                clearance = True
                clearance_start = t
        # Pedestrians cross only parallel to the protected green, at phase start.
        if not clearance and t - phase_started < DT:
            pedestrian_waits.extend(t - a for a in ped_pending[phase])
            ped_pending[phase].clear()
        for approach in range(4):
            lane = sorted(
                (v for v in vehicles if v.approach == approach), key=lambda v: -v.position
            )
            for index, v in enumerate(lane):
                lead = lane[index - 1] if index else None
                target = FREE_SPEED
                obstacle = lead.position - LENGTH - GAP if lead else float("inf")
                allowed = not clearance and approach % 2 == phase
                if not allowed and v.position <= STOP_LINE:
                    obstacle = min(obstacle, STOP_LINE)
                distance = max(obstacle - v.position, 0)
                target = min(target, float(np.sqrt(2 * 2.5 * distance)))
                if distance < 0.3:
                    target = 0
                change = np.clip(target - v.velocity, -3.5 * DT, 2.0 * DT)
                v.velocity = max(0, float(v.velocity + change))
                travel = min(v.velocity * DT, distance)
                v.position += travel
                if travel < v.velocity * DT:
                    v.velocity = travel / DT
                v.delay += DT * (1 - v.velocity / FREE_SPEED)
                is_stopped = v.velocity < 0.5
                if is_stopped and not v.was_stopped and t - v.arrival > 3:
                    v.stops += 1
                v.was_stopped = is_stopped
        exited = [v for v in vehicles if v.position > EXIT]
        complete.extend(exited)
        vehicles = [v for v in vehicles if v.position <= EXIT]
        total_queue = sum(queues)
        max_queue = max(max_queue, total_queue)
        active = complete + vehicles + [v for lane in pending for v in lane]
        delay = sum(v.delay for v in active) + sum(
            max(0, t - v.arrival) for lane in pending for v in lane
        )
        waiting = pedestrian_waits + [t - a for lane in ped_pending for a in lane]
        if record and step % 2 == 0:
            frames.append(
                {
                    "t": t,
                    "phase": phase,
                    "signal": "green"
                    if not clearance
                    else "yellow"
                    if t - clearance_start < settings.yellow
                    else "all_red",
                    "vehicles": [
                        {
                            "id": v.id,
                            "approach": v.approach,
                            "position": round(v.position, 2),
                            "velocity": round(v.velocity, 2),
                        }
                        for v in vehicles
                    ],
                    "metrics": {
                        "delay": round(delay / max(len(active), 1), 2),
                        "queue": total_queue,
                        "cleared": len(complete),
                        "throughput": round(len(complete) * 3600 / max(t, 1), 1),
                        "stops": round(sum(v.stops for v in active) / max(len(active), 1), 2),
                        "pedestrian_wait": round(float(np.mean(waiting)), 2) if waiting else 0,
                    },
                }
            )
    all_vehicles = complete + vehicles + [v for lane in pending for v in lane]
    total_delay = sum(v.delay for v in all_vehicles) + sum(
        max(0, settings.duration - v.arrival) for lane in pending for v in lane
    )
    all_waits = pedestrian_waits + [settings.duration - a for lane in ped_pending for a in lane]
    metrics = {
        "delay": round(total_delay / max(len(all_vehicles), 1), 3),
        "throughput": len(complete),
        "mean_queue": round(float(np.mean([f["metrics"]["queue"] for f in frames])), 3)
        if frames
        else None,
        "max_queue": max_queue,
        "stops": round(sum(v.stops for v in all_vehicles) / max(len(all_vehicles), 1), 3),
        "pedestrian_wait": round(float(np.mean(all_waits)), 3) if all_waits else 0,
        "arrived": len(all_vehicles),
        "unfinished": len(vehicles) + sum(map(len, pending)),
        "pedestrians_served": len(pedestrian_waits),
        "pedestrians_unserved": sum(map(len, ped_pending)),
        "approach_delay": [
            round(
                float(
                    np.mean(
                        [
                            v.delay
                            + (max(0, settings.duration - v.arrival) if v in pending[i] else 0)
                            for v in all_vehicles
                            if v.approach == i
                        ]
                    )
                ),
                3,
            )
            if any(v.approach == i for v in all_vehicles)
            else 0
            for i in range(4)
        ],
    }
    metrics["objective"] = round(
        metrics["delay"]
        + 0.2 * metrics["pedestrian_wait"]
        + 0.15 * max_queue
        + 0.1 * max(metrics["approach_delay"]),
        3,
    )
    return {
        "policy": policy,
        "greens": fixed if policy != "adaptive" else None,
        "metrics": metrics,
        "frames": frames,
    }


def optimize(settings: SimulationConfig):
    minimum = max(settings.min_green, settings.pedestrian_interval)
    values = sorted(set([minimum, 20, 30, 40, 50, settings.max_green]))
    values = [v for v in values if minimum <= v <= settings.max_green]
    # Training seeds differ from the evaluation seed; each candidate sees equivalent demand.
    tuning_seeds = [settings.seed + 101, settings.seed + 211]
    candidates = []
    for a in values:
        for b in values:
            if a + b + 2 * (settings.yellow + settings.all_red) > 120:
                continue
            objectives = []
            for seed in tuning_seeds:
                tune = settings.model_copy(update={"seed": seed % (2**31)})
                objectives.append(
                    simulate(tune, "atlas", [a, b], record=False)["metrics"]["objective"]
                )
            candidates.append({"greens": [a, b], "objective": float(np.mean(objectives))})
    chosen = min(candidates, key=lambda c: c["objective"])
    runs = [
        simulate(settings, "baseline", [30, 30]),
        simulate(settings, "adaptive"),
        simulate(settings, "atlas", chosen["greens"]),
    ]
    base, improved = runs[0]["metrics"], runs[2]["metrics"]
    change = {
        k: round((base[k] - improved[k]) / base[k] * 100, 2) if base[k] else None
        for k in ["delay", "mean_queue", "stops", "pedestrian_wait"]
    }
    change["throughput"] = (
        round((improved["throughput"] - base["throughput"]) / base["throughput"] * 100, 2)
        if base["throughput"]
        else None
    )
    return {
        "settings": settings.model_dump(),
        "runs": runs,
        "improvement_pct": change,
        "search": {"candidates": len(candidates), "tuning_seeds": tuning_seeds, "selected": chosen},
        "scope": "Single-lane protected straight-through simulation; delays include unfinished demand. Not a field signal recommendation.",
    }
