"""Experimental v4 harness. Existing v2/v3 evidence remains frozen.

Outages hide controller inputs uniformly across adaptive policies. Work directories
are unique so concurrent jobs and ablations cannot overwrite their evidence.
"""

import contextlib
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
from atlas.city_network import binary, sha
from atlas.control import FeedbackController, phase_movements
from atlas.control_v2 import (
    NetworkCoordinator,
    RiskConfig,
    RiskController,
    SafetyGate,
    SafetyProfile,
)
from atlas.control_v4 import NetworkConfig, NetworkController
from atlas.evaluation.signal import FIXED, choose_phase, trip_metrics
from atlas.signal_runtime import selected_profile


class SimulationCancelled(RuntimeError):
    """Only this worker's simulated episode stops; no external hardware."""


def run_network(
    city,
    policy,
    seed,
    duration=300,
    settings=RiskConfig(),
    coordinated=True,
    root=None,
    routes=None,
    scenario="nominal",
    cancel_check=None,
    candidate_settings=NetworkConfig(),
    controller_factory=None,
    controller_source=None,
):
    import psutil
    import traci
    import traci.constants as tc
    from sumolib.miscutils import getFreeSocketPort
    from sumolib.net import readNet

    started = time.perf_counter()
    peak_rss = psutil.Process().memory_info().rss
    root = root or config.ROOT / "datasets/cities" / city
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    net = root / "network.net.xml"
    routes = (
        routes
        or root / f"routes-{manifest['seed']}-{manifest['duration']}-{manifest['period']}.xml"
    )
    # Source generation may serialize 3.0 as 3; manifest is authoritative.
    if not routes.exists():
        matches = [p for p in root.glob("routes-*.xml") if sha(p) == manifest["routes_sha256"]]
        if len(matches) != 1:
            raise ValueError("Cannot identify pinned routes")
        routes = matches[0]
    if sha(net) != manifest["network_sha256"] or sha(routes) != manifest["routes_sha256"]:
        raise ValueError("Network/routes differ from pinned manifest")
    if policy not in {
        "fixed",
        "max_pressure",
        "original_mpc",
        "risk_mpc",
        "network_mpc",
        "actuated",
        "learned_mpc",
        "marl",
    }:
        raise ValueError("Unsupported operational controller")
    if policy in {"learned_mpc", "marl"} and controller_factory is None:
        raise ValueError("Learned research policy needs an explicit controller factory")
    if controller_factory is not None and controller_source is None:
        raise ValueError("Factory policy must declare its source path for checksum provenance")
    if scenario not in {"nominal", "sensor_outage", "lane_closure"}:
        raise ValueError("Unknown scenario")
    geographic_network = readNet(str(net))
    route_tree = ET.parse(routes).getroot()
    scheduled = {
        v.attrib["id"]: float(v.attrib["depart"])
        for v in route_tree.findall("vehicle")
        if float(v.attrib["depart"]) < duration
    }
    if not scheduled:
        raise ValueError("No scheduled demand")
    output = (
        config.ROOT
        / "datasets/evaluation-runs/network-v4"
        / f"{city}-{policy}-{seed}-{scenario}-{uuid.uuid4().hex}"
    )
    output.mkdir(parents=True, exist_ok=True)
    trip_file = output / "tripinfo.xml"
    port = getFreeSocketPort()
    command = [
        binary("sumo"),
        "--net-file",
        str(net),
        "--route-files",
        str(routes),
        "--seed",
        str(seed),
        "--step-length",
        "1",
        "--end",
        str(duration),
        "--no-step-log",
        "true",
        "--duration-log.disable",
        "true",
        "--time-to-teleport",
        "-1",
        "--tripinfo-output",
        str(trip_file),
        "--tripinfo-output.write-unfinished",
        "true",
        "--remote-port",
        str(port),
    ]
    connection = None
    with (output / "sumo.log").open("w", encoding="utf-8") as log:
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
            gates, controllers, movements, fixed = {}, {}, {}, {}
            source = ET.parse(net).getroot()
            for logic in source.findall("tlLogic"):
                signal = logic.attrib["id"]
                green = [
                    p
                    for p in logic.findall("phase")
                    if any(c in "Gg" for c in p.attrib["state"])
                    and all(c in "rGgs" for c in p.attrib["state"])
                ]
                states = [p.attrib["state"] for p in green]
                if len(states) < 2:
                    continue
                # Imported SUMO legal source phases; conflict/pedestrian surveys absent.
                gate = SafetyGate(states, SafetyProfile(min_green=10))
                moves = phase_movements(states, connection.trafficlight.getControlledLinks(signal))
                gates[signal], movements[signal] = gate, moves
                fixed[signal] = [max(10, min(60, int(float(p.attrib["duration"])))) for p in green]
                if city == "cologne1":
                    fixed[signal] = FIXED
                controllers[signal] = (
                    controller_factory(moves)
                    if controller_factory is not None
                    else FeedbackController(selected_profile(), moves)
                    if policy == "original_mpc"
                    else NetworkController(moves, candidate_settings)
                    if policy == "network_mpc"
                    else RiskController(moves, settings)
                )
                connection.trafficlight.setRedYellowGreenState(signal, states[0])
            if not gates:
                raise ValueError("No controllable multi-phase signals")
            all_lanes = sorted(
                {
                    lane
                    for moves in movements.values()
                    for phase in moves
                    for pair in phase
                    for lane in pair
                }
            )
            inbound = sorted(
                {a for moves in movements.values() for phase in moves for a, _ in phase}
            )
            caps = {a: max(1, connection.lane.getLength(a) / 7.5) for a in all_lanes}
            for a in all_lanes:
                connection.lane.subscribe(
                    a,
                    [
                        tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
                        tc.LAST_STEP_VEHICLE_NUMBER,
                        tc.LAST_STEP_VEHICLE_ID_LIST,
                    ],
                )
            members = {a: set() for a in all_lanes}
            rates, ages, queues, stops = defaultdict(float), defaultdict(int), [], defaultdict(int)
            since = {signal: [0] * len(gate.states) for signal, gate in gates.items()}
            prior_moving, approach_map, planning = {}, {}, []
            frames, decisions, violations = [], [], 0
            co2_mg = fuel_mg = 0.0
            initial_states = {s: g.states[0] for s, g in gates.items()}
            closed_lane = max(inbound, key=lambda a: caps[a])
            original_max_speed = connection.lane.getMaxSpeed(closed_lane)
            for step in range(duration):
                if cancel_check is not None and step % 5 == 0 and cancel_check():
                    raise SimulationCancelled("Simulation cancelled by the operator")
                peak_rss = max(peak_rss, psutil.Process().memory_info().rss)
                for identity in connection.simulation.getDepartedIDList():
                    connection.vehicle.subscribe(
                        identity,
                        [
                            tc.VAR_SPEED,
                            tc.VAR_POSITION,
                            tc.VAR_LANE_ID,
                            tc.VAR_CO2EMISSION,
                            tc.VAR_FUELCONSUMPTION,
                        ],
                    )
                vehicle_values = connection.vehicle.getAllSubscriptionResults()
                values = connection.lane.getAllSubscriptionResults()
                lanes = {}
                for a in all_lanes:
                    row = values.get(a, {})
                    cars = set(row.get(tc.LAST_STEP_VEHICLE_ID_LIST, []))
                    rates[a] = 0.95 * rates[a] + 0.05 * len(cars - members[a])
                    q = row.get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
                    ages[a] = ages[a] + 1 if q and not members[a] - cars else 0
                    lanes[a] = {
                        "queue": q,
                        "vehicles": row.get(tc.LAST_STEP_VEHICLE_NUMBER, 0),
                        "capacity": caps[a],
                        "arrival_rate": rates[a],
                        "starvation": ages[a],
                        "waiting": 0,
                    }
                    members[a] = cars
                if scenario == "lane_closure" and step == duration // 3:
                    connection.lane.setMaxSpeed(closed_lane, 0.1)
                if scenario == "lane_closure" and step == 2 * duration // 3:
                    connection.lane.setMaxSpeed(closed_lane, original_max_speed)
                sensor_outage = (
                    scenario == "sensor_outage" and duration // 3 <= step < 2 * duration // 3
                )
                view = {} if sensor_outage else lanes
                hints = (
                    NetworkCoordinator().hints(controllers, view)
                    if coordinated
                    and policy in {"risk_mpc", "network_mpc", "learned_mpc", "marl"}
                    and not sensor_outage
                    else {}
                )
                executed, total_queue = {}, sum(lanes[a]["queue"] for a in inbound)
                for signal, gate in gates.items():
                    tick = time.perf_counter()
                    if sensor_outage and policy != "fixed":
                        requested, reason = gate.allowed(step)[0], "common_sensor_fallback"
                    elif policy in {
                        "fixed",
                        "max_pressure",
                        "actuated",
                        "responsive",
                        "coordinated_fixed",
                    }:
                        phase_queues = [
                            sum(lanes[a]["queue"] for a in {a for a, _ in m})
                            for m in movements[signal]
                        ]
                        pressure = [
                            sum(
                                lanes[a]["vehicles"] / caps[a] - lanes[b]["vehicles"] / caps[b]
                                for a, b in m
                            )
                            for m in movements[signal]
                        ]
                        since[signal] = [age + 1 for age in since[signal]]
                        since[signal][gate.current] = 0
                        legacy = (
                            "fixed"
                            if policy == "fixed"
                            else "adaptive"
                            if policy == "actuated"
                            else policy
                        )
                        requested = (
                            choose_phase(
                                legacy,
                                gate.current,
                                step - gate.started,
                                phase_queues,
                                pressure,
                                fixed[signal],
                                since[signal],
                            )
                            if gate.clearance is None
                            else gate.current
                        )
                        reason = "algorithmic_" + policy
                    else:
                        if policy == "original_mpc" and not view:
                            requested, reason = (gate.allowed(step)[0], "sensor_fallback")
                        elif policy == "original_mpc":
                            requested, reason = controllers[signal].decide(step, gate, view)
                        else:
                            requested, reason = controllers[signal].decide(
                                step, gate, view, hints.get(signal)
                            )
                    planning.append((time.perf_counter() - tick) * 1000)
                    lamp, execution = gate.advance(step, int(requested))
                    connection.trafficlight.setRedYellowGreenState(signal, lamp)
                    executed[signal] = {
                        "phase": gate.current,
                        "state": lamp,
                        "execution": execution,
                        "queue": sum(
                            lanes[a]["queue"] for a in {a for m in movements[signal] for a, _ in m}
                        ),
                        "reason": reason,
                    }
                    if (
                        step % 10 == 0
                        and policy in {"risk_mpc", "network_mpc", "learned_mpc", "marl"}
                        and not sensor_outage
                        and controllers[signal].last_explanation
                    ):
                        decisions.append(
                            {"intersection": signal, **controllers[signal].last_explanation}
                        )
                    # Output may only be a legal source state, current yellow, or all-red.
                    violations += int(
                        lamp not in gate.states
                        and lamp != gate.yellow()
                        and lamp != "r" * len(lamp)
                    )
                queues.append(total_queue)
                if step % 5 == 0:
                    frames.append(
                        {
                            "t": step,
                            "queue": total_queue,
                            "arrived": connection.simulation.getArrivedNumber(),
                            "signals": executed,
                            "lane_observations": lanes,
                            "movements": movements,
                            "vehicles": [
                                {
                                    "id": identity,
                                    "lon": geographic_network.convertXY2LonLat(
                                        *vehicle_values[identity][tc.VAR_POSITION]
                                    )[0],
                                    "lat": geographic_network.convertXY2LonLat(
                                        *vehicle_values[identity][tc.VAR_POSITION]
                                    )[1],
                                    "speed_m_s": vehicle_values[identity][tc.VAR_SPEED],
                                }
                                for identity in sorted(vehicle_values)[:1000]
                            ],
                            "vehicle_positions_scope": "Actual SUMO positions, not camera trajectories; at most 1000 active simulated vehicles",
                        }
                    )
                for vehicle, vehicle_state in vehicle_values.items():
                    moving = vehicle_state[tc.VAR_SPEED] >= 0.1
                    if prior_moving.get(vehicle, False) and not moving:
                        stops[vehicle] += 1
                    prior_moving[vehicle] = moving
                    lane = vehicle_state[tc.VAR_LANE_ID]
                    if lane in inbound:
                        approach_map.setdefault(vehicle, lane.rsplit("_", 1)[0])
                    co2_mg += vehicle_state[tc.VAR_CO2EMISSION]
                    fuel_mg += vehicle_state[tc.VAR_FUELCONSUMPTION]
                connection.simulationStep()
            connection.close()
            connection = None
            child.wait(timeout=15)
            if child.returncode:
                raise RuntimeError("SUMO episode failed")
        finally:
            if connection is not None:
                connection.close()
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
    metrics = trip_metrics(
        ET.parse(trip_file).getroot().findall("tripinfo"),
        scheduled,
        duration,
        stops,
        queues,
        approach_map,
    )
    reported_trips = {
        v.attrib["id"]: v.attrib for v in ET.parse(trip_file).getroot().findall("tripinfo")
    }
    all_delays = [
        float(reported_trips[v]["timeLoss"]) + float(reported_trips[v].get("departDelay", 0))
        if v in reported_trips
        else max(0, duration - depart)
        for v, depart in scheduled.items()
    ]
    metrics.update(
        delay_s_p95=float(np.percentile(all_delays, 95)),
        bus_delay_s=None,
        spillback_measurement=None,
        decision_ms_p50=float(np.percentile(planning, 50)),
        decision_ms_p95=float(np.percentile(planning, 95)),
        wall_seconds=time.perf_counter() - started,
        simulation_steps_per_second=duration / (time.perf_counter() - started),
        modeled_safety_violations=violations,
        rejected_requests=sum(g.rejected for g in gates.values()),
        co2_model_kg=co2_mg / 1_000_000,
        fuel_model_kg=fuel_mg / 1_000_000,
        phase_switches=sum(g.switches for g in gates.values()),
        peak_worker_rss_mib=peak_rss / 1024**2,
    )
    result = {
        "city": city,
        "policy": policy,
        "seed": seed,
        "duration": duration,
        "scenario": scenario,
        "coordinated": coordinated,
        "settings": asdict(candidate_settings) if policy == "network_mpc" else asdict(settings),
        "metrics": metrics,
        "initial_states": initial_states,
        "network_sha256": sha(net),
        "routes_sha256": sha(routes),
        "platform": platform.system(),
        "sumo_version": manifest["sumo_version"],
        "controller_sha256": sha(controller_source)
        if controller_source
        else sha(
            config.ROOT
            / "backend/atlas"
            / (
                "control_v4.py"
                if policy == "network_mpc"
                else "control.py"
                if policy == "original_mpc"
                else "control_v2.py"
            )
        ),
        "harness_sha256": sha(__file__),
        "provenance_class": "simulated_outcome",
        "calibration": manifest.get("calibration", {}),
        "trace": frames,
        "decisions": decisions,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        city,
        policy,
        seed,
        scenario,
        round(metrics["mean_delay_s"], 3),
        "s delay",
        round(metrics["wall_seconds"], 1),
        "s wall",
        flush=True,
    )
    return result
