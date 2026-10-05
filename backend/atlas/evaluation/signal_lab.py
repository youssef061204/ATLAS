"""Paired SUMO experiments with per-second diagnostics and unchanged baselines."""

import contextlib
import gzip
import hashlib
import io
import json
import os
import platform
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict

import numpy as np

from atlas import config
from atlas.control import ControlConfig, FeedbackController, SignalMachine, phase_movements
from atlas.evaluation.artifacts import checksum
from atlas.evaluation.data import DATASETS
from atlas.evaluation.signal import FIXED, build_period, choose_phase, trip_metrics


def demand_variant(source, target, begin, duration, variant, seed):
    """Deterministic perturbations before any controller starts; paired by bytes.

    Subsample/replicate source OD trips; bursts change departure timestamps, never
    controller observations. The nominal scenario is byte-for-byte build_period.
    """
    scheduled = build_period(source, target, begin, duration)
    if variant == "nominal":
        return scheduled
    rng = np.random.default_rng(seed)
    root = ET.parse(target).getroot()
    result = ET.Element("routes")
    for element in root:
        if element.tag != "trip":
            result.append(element)
            continue
        identity = element.attrib["id"]
        depart = float(element.attrib["depart"])
        copies = 1
        if variant == "low":
            copies = int(rng.random() < 0.7)
        elif variant == "peak":
            copies += int(rng.random() < 0.3)
        elif variant == "imbalance":
            # Stable OD-origin groups, no selection by observed controller performance.
            group = hashlib.sha256(element.attrib["from"].encode()).digest()[0] % 2
            copies = 1 + int(rng.random() < 0.4) if group == 0 else int(rng.random() < 0.65)
        elif variant == "burst":
            depart = int(depart // 120) * 120 + (depart % 120) * 0.5
        else:
            raise ValueError("Unknown demand perturbation")
        for copy in range(copies):
            trip = ET.fromstring(ET.tostring(element))
            trip.set("id", identity if copy == 0 else f"{identity}_atlas_replica{copy}")
            trip.set("depart", str(min(duration - 0.001, depart + copy * 0.1)))
            result.append(trip)
    types = [e for e in result if e.tag != "trip"]
    trips = sorted(
        (e for e in result if e.tag == "trip"),
        key=lambda e: (float(e.attrib["depart"]), e.attrib["id"]),
    )
    result[:] = types + trips
    ET.ElementTree(result).write(target, encoding="utf-8", xml_declaration=True)
    return {e.attrib["id"]: float(e.attrib["depart"]) for e in trips}


def run(
    policy,
    seed,
    begin=25200,
    duration=1800,
    variant="nominal",
    settings=None,
    scenario="cologne1",
    greens=None,
    reuse=True,
):
    import sumo
    import traci
    import traci.constants as tc
    from sumolib.miscutils import getFreeSocketPort

    started_wall = time.perf_counter()
    root = DATASETS / "resco" / scenario
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if checksum(root / name) != expected:
            raise ValueError("RESCO source checksum mismatch")
    net = root / f"{scenario}.net.xml"
    source = root / f"{scenario}.rou.xml"
    logic = ET.parse(net).getroot().findall("tlLogic")
    if len(logic) != 1:
        raise ValueError("This isolated-junction experiment requires exactly one signal")
    signal_id = logic[0].attrib["id"]
    states = [
        phase.attrib["state"]
        for phase in logic[0].findall("phase")
        if any(c in "Gg" for c in phase.attrib["state"])
        and not any(c in "yY" for c in phase.attrib["state"])
    ]
    settings = settings or ControlConfig()
    greens = greens or (
        FIXED
        if scenario == "cologne1"
        else [
            max(10, min(60, int(float(phase.attrib["duration"]))))
            for phase in logic[0].findall("phase")
            if phase.attrib["state"] in states
        ]
    )
    if policy == "atlas_original" and greens == FIXED:
        greens = [12, 12, 40, 12, 12, 12, 40, 12]
    if len(greens) != len(states) or any(not 10 <= g <= 60 for g in greens):
        raise ValueError("Invalid baseline timing")
    signature = {
        "scenario": scenario,
        "source": manifest["files"],
        "seed": seed,
        "begin": begin,
        "duration": duration,
        "warmup": 0,
        "teleport": -1,
        "variant": variant,
        "policy": policy,
        "greens": greens,
        "settings": asdict(settings),
        "sumo": "1.27.1",
        "platform": platform.system(),
        "routing": "Policy-independent duarouter paths before the episode",
        "harness_sha256": checksum(config.ROOT / "backend/atlas/evaluation/signal_lab.py"),
        "controller_sha256": checksum(config.ROOT / "backend/atlas/control.py"),
    }
    identity = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:20]
    directory = DATASETS / "evaluation-runs" / "signal-v2" / identity
    directory.mkdir(parents=True, exist_ok=True)
    cached = directory / "metrics.json"
    if reuse and cached.exists():
        result = json.loads(cached.read_text(encoding="utf-8"))
        if result["signature"] == signature:
            return result
    routes = directory / "period.rou.xml"
    scheduled = demand_variant(source, routes, begin, duration, variant, seed)
    trips_path = directory / "tripinfo.xml"
    # Resolve OD trips before control begins. Each policy receives the same paths,
    # rather than allowing departure-time routing to depend on its traffic state.
    routed = directory / "resolved.rou.xml"
    router = str(
        __import__("pathlib").Path(sumo.SUMO_HOME)
        / "bin"
        / ("duarouter.exe" if os.name == "nt" else "duarouter")
    )
    subprocess.run(
        [
            router,
            "--net-file",
            str(net),
            "--route-files",
            str(routes),
            "--output-file",
            str(routed),
            "--seed",
            str(seed),
            "--no-step-log",
            "true",
        ],
        check=True,
        capture_output=True,
    )
    route_tree = ET.parse(routed)
    route_tree.write(routed, encoding="utf-8", xml_declaration=True)
    port = getFreeSocketPort()
    binary = str(
        __import__("pathlib").Path(sumo.SUMO_HOME)
        / "bin"
        / ("sumo.exe" if os.name == "nt" else "sumo")
    )
    command = [
        binary,
        "--net-file",
        str(net),
        "--route-files",
        str(routed),
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
    with (directory / "sumo.log").open("w", encoding="utf-8") as log:
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
            links = connection.trafficlight.getControlledLinks(signal_id)
            movements = phase_movements(states, links)
            inbound = sorted({a for moves in movements for a, b in moves})
            all_lanes = sorted({lane for moves in movements for pair in moves for lane in pair})
            capacities = {a: max(connection.lane.getLength(a) / 7.5, 1) for a in all_lanes}
            for lane in all_lanes:
                connection.lane.subscribe(
                    lane,
                    [
                        tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
                        tc.LAST_STEP_VEHICLE_NUMBER,
                        tc.LAST_STEP_OCCUPANCY,
                        tc.LAST_STEP_VEHICLE_ID_LIST,
                    ],
                )
            machine = SignalMachine(states)
            controller = FeedbackController(settings, movements)
            connection.trafficlight.setRedYellowGreenState(signal_id, states[0])
            applied_state = states[0]
            since_service = [0] * len(states)
            stops, previously_moving, approach_map = defaultdict(int), {}, {}
            last_members = {a: set() for a in all_lanes}
            arrival_rate, lane_ages = defaultdict(float), defaultdict(int)
            last_loss, insertion_delay, previous_lane, origin_lane = {}, {}, {}, {}
            lane_turns = defaultdict(int)
            queues, trace, requested_counts = [], [], defaultdict(int)
            cumulative_objective, queue_area, wasted_green, planning_times = 0.0, 0.0, 0, []
            full_log = directory / "steps.jsonl.gz"
            with gzip.open(full_log, "wt", encoding="utf-8", compresslevel=3) as diagnostics:
                for step in range(duration):
                    if connection.simulation.getTime() != step:
                        raise ValueError("Stale or advanced observation timestamp")
                    values = connection.lane.getAllSubscriptionResults()
                    observed = connection.vehicle.getAllSubscriptionResults()
                    waiting = defaultdict(float)
                    for vehicle, row in observed.items():
                        lane = row.get(tc.VAR_LANE_ID)
                        waiting[lane] += row.get(tc.VAR_WAITING_TIME, 0)
                        last_loss[vehicle] = row.get(tc.VAR_TIMELOSS, 0)
                        old_lane = previous_lane.get(vehicle)
                        if old_lane in inbound and lane != old_lane:
                            origin_lane[vehicle] = old_lane
                        if lane in all_lanes and lane not in inbound and vehicle in origin_lane:
                            lane_turns[(origin_lane.pop(vehicle), lane)] += 1
                        previous_lane[vehicle] = lane
                    lanes, arrivals, departures = {}, {}, {}
                    for lane in all_lanes:
                        row = values.get(lane, {})
                        members = set(row.get(tc.LAST_STEP_VEHICLE_ID_LIST, []))
                        arrivals[lane] = len(members - last_members[lane])
                        departures[lane] = len(last_members[lane] - members)
                        arrival_rate[lane] = 0.95 * arrival_rate[lane] + 0.05 * arrivals[lane]
                        queue = row.get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
                        lane_ages[lane] = (
                            lane_ages[lane] + 1 if queue > 0 and departures[lane] == 0 else 0
                        )
                        lanes[lane] = {
                            "queue": queue,
                            "vehicles": row.get(tc.LAST_STEP_VEHICLE_NUMBER, 0),
                            "capacity": capacities[lane],
                            "waiting": waiting[lane],
                            "occupancy": row.get(tc.LAST_STEP_OCCUPANCY, 0) / 100,
                            "arrival_rate": arrival_rate[lane],
                            "starvation": lane_ages[lane],
                        }
                        last_members[lane] = members
                    phase_queues = [
                        sum(lanes[a]["queue"] for a in {a for a, b in moves}) for moves in movements
                    ]
                    pressure = [
                        sum(
                            lanes[a]["vehicles"] / capacities[a]
                            - lanes[b]["vehicles"] / capacities[b]
                            for a, b in moves
                        )
                        for moves in movements
                    ]
                    since_service = [age + 1 for age in since_service]
                    elapsed = step - machine.started
                    if machine.clearance is not None:
                        requested, reason = machine.current, "clearance"
                    elif policy in {
                        "fixed",
                        "atlas_original",
                        "max_pressure",
                        "adaptive",
                        "atlas_fixed_equivalent",
                    }:
                        since_service[machine.current] = 0
                        legacy = (
                            "atlas"
                            if policy in {"atlas_original", "atlas_fixed_equivalent"}
                            else policy
                        )
                        requested = choose_phase(
                            legacy,
                            machine.current,
                            elapsed,
                            phase_queues,
                            pressure,
                            greens,
                            since_service,
                        )
                        reason = (
                            "legacy_cycle"
                            if legacy in {"atlas", "fixed"}
                            else "legacy_pressure_or_queue"
                        )
                    else:
                        tick = time.perf_counter()
                        requested, reason = controller.decide(step, machine, lanes)
                        planning_times.append((time.perf_counter() - tick) * 1000)
                    requested_counts[requested] += 1
                    state, execution = machine.advance(step, requested)
                    if execution == "green_started":
                        since_service[machine.current] = 0
                    if state != applied_state:
                        connection.trafficlight.setRedYellowGreenState(signal_id, state)
                        applied_state = state
                    queue = sum(lanes[a]["queue"] for a in inbound)
                    queues.append(queue)
                    queue_area += queue
                    transition_cost = 5 if execution == "switch" else 0
                    cumulative_objective += queue + transition_cost
                    if (
                        machine.clearance is None
                        and all(lanes[a]["vehicles"] == 0 for a, _ in movements[machine.current])
                        and queue > 0
                    ):
                        wasted_green += 1
                    not_inserted_delay = sum(
                        max(0, step - depart)
                        for v, depart in scheduled.items()
                        if v not in insertion_delay
                    )
                    total_delay = (
                        sum(last_loss.values()) + sum(insertion_delay.values()) + not_inserted_delay
                    )
                    frame = {
                        "t": step,
                        "observation_time": step,
                        "phase": machine.current,
                        "requested_phase": requested,
                        "executed_state": state,
                        "phase_duration": step - machine.started,
                        "time_since_last_switch": None
                        if machine.switches == 0
                        else step
                        - (
                            machine.clearance
                            if machine.clearance is not None
                            else machine.started - 5
                        ),
                        "clearance": machine.clearance is not None,
                        "target_phase": machine.target,
                        "lanes": lanes,
                        "arrivals": arrivals,
                        "departures": departures,
                        "pressure_by_phase": pressure,
                        "controller_score": controller.last_scores.tolist(),
                        "total_pressure": float(sum(pressure)),
                        "total_delay_s": total_delay,
                        "throughput": connection.simulation.getArrivedNumber(),
                        "queue": queue,
                        "queue_area": queue_area,
                        "cumulative_objective": cumulative_objective,
                        "reward_components": {"queue": -queue, "transition": -transition_cost},
                        "reason": reason,
                        "execution": execution,
                        "switches": machine.switches,
                        "yellow_seconds": machine.yellow_seconds,
                        "all_red_seconds": machine.all_red_seconds,
                        "starved_lanes": [a for a in inbound if lane_ages[a] >= 180],
                        "cumulative_departures": sum(1 for a in last_loss if a not in observed),
                    }
                    diagnostics.write(json.dumps(frame, separators=(",", ":")) + "\n")
                    if step % 5 == 0:
                        trace.append(
                            {
                                k: v
                                for k, v in frame.items()
                                if k not in {"lanes", "arrivals", "departures", "controller_score"}
                            }
                            | {
                                "lane_queues": {a: lanes[a]["queue"] for a in inbound},
                                "lane_waiting": {a: lanes[a]["waiting"] for a in inbound},
                            }
                        )
                    connection.simulationStep()
                    for vehicle in connection.simulation.getDepartedIDList():
                        insertion_delay[vehicle] = max(
                            0, connection.vehicle.getDeparture(vehicle) - scheduled[vehicle]
                        )
                        connection.vehicle.subscribe(
                            vehicle,
                            [tc.VAR_SPEED, tc.VAR_LANE_ID, tc.VAR_WAITING_TIME, tc.VAR_TIMELOSS],
                        )
                    for vehicle, row in connection.vehicle.getAllSubscriptionResults().items():
                        moving = row.get(tc.VAR_SPEED, 0) >= 0.1
                        if previously_moving.get(vehicle, False) and not moving:
                            stops[vehicle] += 1
                        previously_moving[vehicle] = moving
                        if row.get(tc.VAR_LANE_ID) in inbound:
                            approach_map.setdefault(vehicle, row[tc.VAR_LANE_ID].rsplit("_", 1)[0])
            connection.close()
            connection = None
            child.wait(timeout=15)
            if child.returncode:
                raise RuntimeError("SUMO failed: " + str(directory / "sumo.log"))
        finally:
            if connection is not None:
                connection.close()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
    metrics = trip_metrics(
        ET.parse(trips_path).getroot().findall("tripinfo"),
        scheduled,
        duration,
        stops,
        queues,
        approach_map,
    )
    metrics.update(
        {
            "phase_switches": machine.switches,
            "lost_transition_seconds": machine.yellow_seconds + machine.all_red_seconds,
            "yellow_seconds": machine.yellow_seconds,
            "all_red_seconds": machine.all_red_seconds,
            "wasted_green_seconds": wasted_green,
            "cumulative_queue_vehicle_seconds": queue_area,
            "decision_ms_p95": float(np.percentile(planning_times, 95)) if planning_times else 0,
            "wall_seconds": time.perf_counter() - started_wall,
        }
    )
    result = {
        "signature": signature,
        "metrics": metrics,
        "trace": trace,
        "scheduled_demand_sha256": checksum(routes),
        "resolved_routes_sha256": checksum(routed),
        "initial_state": states[0],
        "states": states,
        "phase_movements": json.loads(json.dumps(movements)),
        "turn_counts": {f"{a}->{b}": v for (a, b), v in lane_turns.items()},
        "diagnostics_file": str(full_log.relative_to(DATASETS)),
        "diagnostics_sha256": checksum(full_log),
    }
    cached.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"{scenario} {variant} {policy} seed {seed}: {metrics['mean_delay_s']:.3f}s, {metrics['completed_trips']}/{len(scheduled)}, {metrics['wall_seconds']:.1f}s wall",
        flush=True,
    )
    return result


def assert_paired(runs):
    reference = runs[0]
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
    for run in runs[1:]:
        if (
            any(run["signature"][k] != reference["signature"][k] for k in keys)
            or run["scheduled_demand_sha256"] != reference["scheduled_demand_sha256"]
            or run.get("resolved_routes_sha256") != reference.get("resolved_routes_sha256")
        ):
            raise ValueError("Unpaired controller comparison")
        if (
            run["initial_state"] != reference["initial_state"]
            or run["states"] != reference["states"]
            or run["phase_movements"] != reference["phase_movements"]
        ):
            raise ValueError("Signal topology/initialization mismatch")
    return True
