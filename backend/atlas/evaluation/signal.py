"""RESCO Cologne1 evaluation with protected phase transitions and held-out demand time."""

import contextlib
import io
import json
import os
import subprocess
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np

from atlas.evaluation.artifacts import checksum, write_artifact
from atlas.evaluation.data import DATASETS, RESCO_REVISION

SIGNAL = "cluster_357187_359543"
FIXED = [10, 10, 40, 10, 10, 10, 40, 10]
# Finite candidates declared before evaluation. Auxiliary turn phases stay at 12 s.
CANDIDATES = [(24, 24), (24, 40), (24, 56), (40, 24), (40, 40), (56, 24)]


def choose_phase(policy, current, elapsed, queues, pressures, greens, since_service):
    if policy in {"fixed", "atlas"}:
        return (current + 1) % len(greens) if elapsed >= greens[current] else current
    if elapsed < 12:
        return current
    if policy == "adaptive":
        other = [q for i, q in enumerate(queues) if i != current]
        return (
            (current + 1) % len(greens)
            if elapsed >= 60
            or max(other) > queues[current] + 2
            or queues[current] == 0
            and max(other) > 0
            else current
        )
    # Max-pressure form: maximize inbound minus downstream density, with bounded starvation.
    starved = [i for i, age in enumerate(since_service) if age >= 180 and queues[i] > 0]
    if starved:
        return max(starved, key=lambda i: since_service[i])
    best = int(np.argmax(pressures))
    if elapsed >= 60:
        alternatives = [i for i in range(len(greens)) if i != current]
        return max(alternatives, key=lambda i: pressures[i])
    return best if pressures[best] > pressures[current] + 1 else current


def build_period(source, destination, begin, duration):
    root = ET.parse(source).getroot()
    selected = ET.Element("routes")
    for element in root:
        if element.tag == "vType":
            selected.append(element)
        elif element.tag == "trip" and begin <= float(element.attrib["depart"]) < begin + duration:
            element.set("depart", str(float(element.attrib["depart"]) - begin))
            selected.append(element)
    ET.ElementTree(selected).write(destination, encoding="utf-8", xml_declaration=True)
    return {e.attrib["id"]: float(e.attrib["depart"]) for e in selected if e.tag == "trip"}


def trip_metrics(trips, scheduled, duration, stops, queues, approach_map):
    reported = {trip.attrib["id"]: trip.attrib for trip in trips}
    delays, travel, completed_delays, groups = [], [], [], defaultdict(list)
    completed = 0
    for identity, depart in scheduled.items():
        trip = reported.get(identity)
        if trip is None:
            delay = max(0, duration - depart)
        else:
            delay = float(trip["timeLoss"]) + float(trip.get("departDelay", 0))
            if float(trip["arrival"]) >= 0:
                completed += 1
                completed_delays.append(delay)
                travel.append(float(trip["duration"]) + float(trip.get("departDelay", 0)))
        delays.append(delay)
        if identity in approach_map:
            groups[approach_map[identity]].append(delay)
    approach_delays = {lane: float(np.mean(values)) for lane, values in groups.items()}
    metrics = {
        "mean_delay_s": float(np.mean(delays)),
        "median_delay_s": float(np.median(delays)),
        "completed_trip_mean_delay_s": float(np.mean(completed_delays))
        if completed_delays
        else None,
        "completed_trips": completed,
        "throughput_vehicles_per_hour": completed * 3600 / duration,
        "scheduled_vehicles": len(scheduled),
        "reported_vehicles": len(reported),
        "not_inserted": len(scheduled) - len(reported),
        "unfinished_vehicles": len(scheduled) - completed,
        "mean_queue": float(np.mean(queues)),
        "max_queue": int(max(queues)),
        "stops_per_vehicle": sum(stops.values()) / max(len(scheduled), 1),
        "completed_mean_travel_time_s": float(np.mean(travel)) if travel else None,
        "pedestrian_wait_s": None,
        "approach_mean_delay_s": approach_delays,
        "worst_observed_approach_delay_s": max(approach_delays.values(), default=0),
    }
    # Same ATLAS objective family, excluding absent pedestrian demand explicitly.
    metrics["objective"] = (
        metrics["mean_delay_s"]
        + 0.15 * metrics["max_queue"]
        + 0.1 * metrics["worst_observed_approach_delay_s"]
    )
    return metrics


def run_sumo(policy, seed, begin, duration=1800, greens=None, reuse=True):
    import sumo
    import traci
    import traci.constants as tc
    from sumolib.miscutils import getFreeSocketPort

    root = DATASETS / "resco" / "cologne1"
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if checksum(root / name) != expected:
            raise ValueError("RESCO source checksum mismatch")
    greens = greens or FIXED
    directory = (
        DATASETS
        / "evaluation-runs"
        / "resco"
        / f"{begin}-{duration}-{seed}-{policy}-{'_'.join(map(str, greens))}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / "metrics.json"
    signature = {
        "network_sha": manifest["files"]["cologne1.net.xml"],
        "demand_sha": manifest["files"]["cologne1.rou.xml"],
        "policy": policy,
        "seed": seed,
        "begin": begin,
        "duration": duration,
        "greens": greens,
        "adapter": "atlas-resco-v1",
    }
    if reuse and cache.exists():
        result = json.loads(cache.read_text())
        if result["signature"] == signature:
            return result
    routes = directory / "period.rou.xml"
    scheduled = build_period(root / "cologne1.rou.xml", routes, begin, duration)
    states = [
        phase.attrib["state"]
        for phase in ET.parse(root / "cologne1.net.xml").getroot().find("tlLogic").findall("phase")
    ]
    port = getFreeSocketPort()
    trips_path = directory / "tripinfo.xml"
    binary = Path(sumo.SUMO_HOME) / "bin" / ("sumo.exe" if os.name == "nt" else "sumo")
    command = [
        str(binary),
        "--net-file",
        str(root / "cologne1.net.xml"),
        "--route-files",
        str(routes),
        "--begin",
        "0",
        "--end",
        str(duration),
        "--step-length",
        "1",
        "--seed",
        str(seed),
        "--tripinfo-output",
        str(trips_path),
        "--tripinfo-output.write-unfinished",
        "true",
        "--no-step-log",
        "true",
        "--duration-log.disable",
        "true",
        "--time-to-teleport",
        "-1",
        "--remote-port",
        str(port),
    ]
    connection = None
    with (directory / "sumo.log").open("w") as log:
        child = subprocess.Popen(
            command,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                connection = traci.connect(
                    port, numRetries=30, waitBetweenRetries=0.1, label=uuid.uuid4().hex, proc=child
                )
            links = connection.trafficlight.getControlledLinks(SIGNAL)
            inbound = sorted({link[0] for group in links for link in group})
            all_lanes = sorted({lane for group in links for link in group for lane in link[:2]})
            capacities = {lane: max(connection.lane.getLength(lane) / 7.5, 1) for lane in all_lanes}
            phase_movements = []
            for state in states:
                phase_movements.append(
                    {
                        (link[0], link[1])
                        for i, group in enumerate(links)
                        if state[i] in "Gg"
                        for link in group
                    }
                )
            for lane in all_lanes:
                connection.lane.subscribe(
                    lane, [tc.LAST_STEP_VEHICLE_HALTING_NUMBER, tc.LAST_STEP_VEHICLE_NUMBER]
                )
            current, started, target, clearance = 0, 0, 0, None
            since_service = [0] * len(states)
            connection.trafficlight.setRedYellowGreenState(SIGNAL, states[current])
            stops, previously_moving, approach_map = defaultdict(int), {}, {}
            queue_series, trace = [], []
            for step in range(duration):
                lane_values = connection.lane.getAllSubscriptionResults()
                halted = {
                    lane: lane_values.get(lane, {}).get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
                    for lane in all_lanes
                }
                density = {
                    lane: lane_values.get(lane, {}).get(tc.LAST_STEP_VEHICLE_NUMBER, 0)
                    / capacities[lane]
                    for lane in all_lanes
                }
                phase_queues = [
                    sum(halted[lane] for lane in {a for a, b in moves}) for moves in phase_movements
                ]
                pressure = [
                    sum(density[a] - density[b] for a, b in moves) for moves in phase_movements
                ]
                elapsed = step - started
                since_service = [age + 1 for age in since_service]
                if clearance is not None:
                    age = step - clearance
                    if age == 3:
                        connection.trafficlight.setRedYellowGreenState(SIGNAL, "r" * len(states[0]))
                    if age >= 5:
                        current, started, clearance = target, step, None
                        since_service[current] = 0
                        connection.trafficlight.setRedYellowGreenState(SIGNAL, states[current])
                else:
                    since_service[current] = 0
                    target = choose_phase(
                        policy, current, elapsed, phase_queues, pressure, greens, since_service
                    )
                    if target != current:
                        clearance = step
                        yellow = "".join("y" if color in "Gg" else "r" for color in states[current])
                        connection.trafficlight.setRedYellowGreenState(SIGNAL, yellow)
                connection.simulationStep()
                for identity in connection.simulation.getDepartedIDList():
                    connection.vehicle.subscribe(identity, [tc.VAR_SPEED, tc.VAR_LANE_ID])
                observations = connection.vehicle.getAllSubscriptionResults()
                for identity, observed in observations.items():
                    moving = observed.get(tc.VAR_SPEED, 0) >= 0.1
                    if previously_moving.get(identity, False) and not moving:
                        stops[identity] += 1
                    previously_moving[identity] = moving
                    lane = observed.get(tc.VAR_LANE_ID)
                    if lane in inbound:
                        approach_map.setdefault(identity, lane.rsplit("_", 1)[0])
                queue_series.append(sum(halted[lane] for lane in inbound))
                if step % 10 == 0:
                    trace.append(
                        {
                            "t": step,
                            "phase": current,
                            "clearance": clearance is not None,
                            "queue": queue_series[-1],
                        }
                    )
            connection.close()
            connection = None
            child.wait(timeout=15)
            if child.returncode:
                raise RuntimeError("SUMO failed; inspect " + str(directory / "sumo.log"))
        finally:
            if connection:
                connection.close()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
    trip_records = ET.parse(trips_path).getroot().findall("tripinfo")
    result = {
        "signature": signature,
        "metrics": trip_metrics(
            trip_records, scheduled, duration, stops, queue_series, approach_map
        ),
        "trace": trace,
        "scheduled_demand_sha256": checksum(routes),
        "sumo_log": str((directory / "sumo.log").relative_to(DATASETS)),
    }
    cache.write_text(json.dumps(result, indent=2))
    print(
        f"Cologne {policy} seed {seed} period {begin}: delay {result['metrics']['mean_delay_s']:.2f} s; cleared {result['metrics']['completed_trips']}/{len(scheduled)}",
        flush=True,
    )
    return result


def evaluate_signal_control():
    tuning_seeds, test_seeds = [1001, 2002], [42, 43, 44]
    search = []
    for a, b in CANDIDATES:
        greens = [12, 12, a, 12, 12, 12, b, 12]
        values = [run_sumo("atlas", seed, 25200, greens=greens) for seed in tuning_seeds]
        search.append(
            {
                "greens": greens,
                "mean_tuning_objective": float(
                    np.mean([v["metrics"]["objective"] for v in values])
                ),
            }
        )
    selected = min(search, key=lambda candidate: candidate["mean_tuning_objective"])["greens"]
    runs = []
    for seed in test_seeds:
        paired = {
            policy: run_sumo(policy, seed, 27000, greens=selected if policy == "atlas" else None)
            for policy in ["fixed", "adaptive", "max_pressure", "atlas"]
        }
        if len({p["scheduled_demand_sha256"] for p in paired.values()}) != 1:
            raise ValueError("Controller demand mismatch")
        runs.append({"seed": seed, "controllers": paired})
    aggregate = {}
    keys = [
        "mean_delay_s",
        "median_delay_s",
        "completed_trips",
        "throughput_vehicles_per_hour",
        "mean_queue",
        "max_queue",
        "stops_per_vehicle",
        "completed_mean_travel_time_s",
        "worst_observed_approach_delay_s",
    ]
    for policy in ["fixed", "adaptive", "max_pressure", "atlas"]:
        aggregate[policy] = {
            key: {
                "mean": float(np.mean([r["controllers"][policy]["metrics"][key] for r in runs])),
                "std": float(
                    np.std([r["controllers"][policy]["metrics"][key] for r in runs], ddof=1)
                ),
            }
            for key in keys
        }
    reductions = [
        (
            r["controllers"]["fixed"]["metrics"]["mean_delay_s"]
            - r["controllers"]["atlas"]["metrics"]["mean_delay_s"]
        )
        / r["controllers"]["fixed"]["metrics"]["mean_delay_s"]
        * 100
        for r in runs
    ]
    return write_artifact(
        "realistic_signal_control",
        benchmark_type="signal_control",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1",
        dataset_version=RESCO_REVISION,
        model="Fixed / ATLAS adaptive heuristic / density max-pressure / ATLAS constrained search",
        seed=test_seeds,
        split={
            "tuning_period": "07:00–07:30 (25200–27000 source seconds)",
            "tuning_seeds": tuning_seeds,
            "test_period": "07:30–08:00 (27000–28800 source seconds)",
            "test_seeds": test_seeds,
        },
        metrics={
            "controllers": aggregate,
            "mean_delay_reduction_pct": float(np.mean(reductions)),
            "delay_reduction_std_pct": float(np.std(reductions, ddof=1)),
            "runs_per_controller": len(test_seeds),
        },
        scope="Published Cologne SUMO network and modeled demand derived from real-world data; simulated interventions, not measured field delay improvements. Held-out demand period and seeds.",
        methodology={
            "sumo": "1.27.1",
            "step_seconds": 1,
            "clearance": "3-second yellow + 2-second all red for every phase transition",
            "fixed": "RESCO phase allocation [2,2,8,2,2,2,8,2] at 5-second action interval, with explicit clearance",
            "adaptive": "Production queue-responsive min/max-green rule generalized from two to eight legal Cologne phases, sequential rotation",
            "max_pressure": "Inbound-minus-downstream lane-density pressure over permitted movements; 12-second min green, 60-second max and 180-second demand-bearing starvation bound. A max-pressure variant, not an exact published score reproduction.",
            "atlas": "Same constrained-search approach and vehicle delay/queue/fairness objective; legal eight-phase network adapter, six predeclared timing candidates. No test selection.",
            "delay": "SUMO timeLoss+departDelay for inserted completed/unfinished trips; horizon-depart for not-inserted demand, mean over every scheduled vehicle",
            "queues": "Stopped vehicles (<0.1 m/s) on controlled inbound lanes, not a full network/off-network queue measure",
            "travel": "Completed trips only; completion and unfinished counts included beside it",
            "pedestrians": "Absent from published scenario; no pedestrian wait claim",
            "demand": "Unmodified source trip OD/time windows; same exact schedule and seed paired across controllers; no teleportation",
        },
        results={"selected_greens": selected, "search": search, "runs": runs},
    )
