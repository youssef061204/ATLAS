"""Assumption-labeled RSM alignment ablation on the unchanged ATLAS 7 network.

The phase order, yellow and clearance durations below deliberately match the
ATLAS 7 approximate model. Only the choice of RSM split record changes.
These states are *not* independently verified lamp observations.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from atlas.rsm_v8 import RsmCycle, completed_cycle_at


def approximate_stage(clock_s: float, rows: list[RsmCycle]) -> str:
    row = completed_cycle_at(rows, int(clock_s * 10) / 10)
    age = clock_s - row.start_s
    main_split = row.phase_split_s[1]
    if main_split >= row.cycle_s:
        return "main"
    green = min(main_split, row.cycle_s - 8.5)
    if age < green:
        return "main"
    if age < green + 3.5:
        return "main_yellow"
    if age < green + 4.5 or age >= row.cycle_s - 1:
        return "red"
    if age >= row.cycle_s - 4:
        return "cross_yellow"
    return "cross"


def write_approximate_signal_program(
    network: ET.ElementTree, rows: list[RsmCycle], seconds: int
) -> dict:
    """Change only the stage sequence in an already built SUMO network."""
    root = network.getroot()
    logic = root.find("tlLogic")
    if logic is None or logic.get("id") != "J":
        raise ValueError("Expected the single ATLAS 7 J traffic light")
    connections = [node for node in root.findall("connection") if node.get("tl") == "J"]
    size = max(int(node.get("linkIndex")) for node in connections) + 1
    old_states = {phase.get("state") for phase in logic.findall("phase")}

    def state(stage: str) -> str:
        values = ["r"] * size
        for connection in connections:
            main = connection.get("from", "")[0] in "NS"
            selected = (stage.startswith("main") and main) or (
                stage.startswith("cross") and not main
            )
            if selected:
                values[int(connection.get("linkIndex"))] = (
                    "y"
                    if stage.endswith("yellow")
                    else "G"
                    if connection.get("dir") == "s"
                    else "g"
                )
        return "".join(values)

    phases: list[list[object]] = []
    clock_origin_s = 8 * 3600 + 27 * 60 + 34
    for tick in range(seconds * 10):
        label = approximate_stage(clock_origin_s + tick / 10, rows)
        values = state(label)
        if values not in old_states:
            raise ValueError("Corrected alignment introduced a new link state")
        if phases and phases[-1][0] == values:
            phases[-1][1] += 1
        else:
            phases.append([values, 1])
    for child in list(logic):
        logic.remove(child)
    for values, ticks in phases:
        ET.SubElement(logic, "phase", duration=f"{ticks / 10:.1f}", state=values)
    return {
        "program_duration_s": seconds,
        "phase_entries": len(phases),
        "unique_link_states": len({values for values, _ in phases}),
        "scope": "Same approximate two-stage link states and clearance timing as v7; RSM cycle-end row alignment only",
    }
