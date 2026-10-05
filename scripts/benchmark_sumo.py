"""Optional independent SUMO validation of baseline and surrogate-selected green splits."""

import argparse
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from atlas import config
from atlas.experiments import save
from atlas.schemas import SimulationConfig
from atlas.simulation import arrivals


def write_xml(path, root):
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main(seed):
    try:
        import sumo
    except ImportError as exc:
        raise SystemExit("Install optional SUMO with: pip install eclipse-sumo==1.27.1") from exc
    executable = ".exe" if __import__("os").name == "nt" else ""
    binaries = Path(sumo.SUMO_HOME) / "bin"
    artifact = json.loads((config.ARTIFACTS / "simulation.json").read_text())
    selected = next((run for run in artifact["runs"] if run["seed"] == seed), None)
    if selected is None:
        raise SystemExit("Run atlas evaluate --only simulation with the standard seeds first")
    settings = SimulationConfig.model_validate(selected["settings"])
    policies = {"baseline": [30, 30], "atlas_surrogate": selected["search"]["selected"]["greens"]}
    results = {}
    with tempfile.TemporaryDirectory(prefix="atlas-sumo-") as directory:
        folder = Path(directory)
        nodes, edges, connections = (
            ET.Element("nodes"),
            ET.Element("edges"),
            ET.Element("connections"),
        )
        ET.SubElement(nodes, "node", id="C", x="0", y="0", type="traffic_light")
        coordinates = [(0, 120), (120, 0), (0, -120), (-120, 0)]
        for i, (x, y) in enumerate(coordinates):
            ET.SubElement(nodes, "node", id=f"A{i}", x=str(x), y=str(y))
            ET.SubElement(
                edges,
                "edge",
                id=f"in{i}",
                attrib={"from": f"A{i}", "to": "C", "numLanes": "1", "speed": "12"},
            )
            ET.SubElement(
                edges,
                "edge",
                id=f"out{i}",
                attrib={"from": "C", "to": f"A{i}", "numLanes": "1", "speed": "12"},
            )
            ET.SubElement(
                connections,
                "connection",
                attrib={
                    "from": f"in{i}",
                    "to": f"out{(i + 2) % 4}",
                    "fromLane": "0",
                    "toLane": "0",
                    "tl": "C",
                    "linkIndex": str(i),
                },
            )
        for name, root in [
            ("nodes.nod.xml", nodes),
            ("edges.edg.xml", edges),
            ("connections.con.xml", connections),
        ]:
            write_xml(folder / name, root)
        subprocess.run(
            [
                str(binaries / f"netconvert{executable}"),
                "--node-files",
                str(folder / "nodes.nod.xml"),
                "--edge-files",
                str(folder / "edges.edg.xml"),
                "--connection-files",
                str(folder / "connections.con.xml"),
                "--output-file",
                str(folder / "network.net.xml"),
                "--no-turnarounds",
                "true",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        routes = ET.Element("routes")
        for kind, length in [("car", 4.5), ("truck", 8), ("bus", 10), ("motorcycle", 2.5)]:
            ET.SubElement(
                routes,
                "vType",
                id=kind,
                length=str(length),
                maxSpeed="12",
                accel="2",
                decel="3.5",
                sigma="0",
                minGap="2.5",
            )
        for i in range(4):
            ET.SubElement(routes, "route", id=f"r{i}", edges=f"in{i} out{(i + 2) % 4}")
        rng = np.random.default_rng(seed + 19)
        demand, _ = arrivals(settings)
        for i, (t, approach) in enumerate(demand):
            kind = str(
                rng.choice(["car", "truck", "bus", "motorcycle"], p=[0.86, 0.07, 0.04, 0.03])
            )
            ET.SubElement(
                routes,
                "vehicle",
                id=f"v{i}",
                type=kind,
                route=f"r{approach}",
                depart=f"{t:.4f}",
                departSpeed="max",
            )
        write_xml(folder / "demand.rou.xml", routes)
        for policy, greens in policies.items():
            additional = ET.Element("additional")
            signal = ET.SubElement(
                additional, "tlLogic", id="C", type="static", programID="atlas", offset="0"
            )
            for duration, state in [
                (greens[0], "GrGr"),
                (settings.yellow, "yryr"),
                (settings.all_red, "rrrr"),
                (greens[1], "rGrG"),
                (settings.yellow, "ryry"),
                (settings.all_red, "rrrr"),
            ]:
                ET.SubElement(signal, "phase", duration=str(duration), state=state)
            write_xml(folder / "signals.add.xml", additional)
            trips = folder / "trips.xml"
            completed = subprocess.run(
                [
                    str(binaries / f"sumo{executable}"),
                    "--net-file",
                    str(folder / "network.net.xml"),
                    "--route-files",
                    str(folder / "demand.rou.xml"),
                    "--additional-files",
                    str(folder / "signals.add.xml"),
                    "--end",
                    str(settings.duration),
                    "--seed",
                    str(seed),
                    "--step-length",
                    ".5",
                    "--tripinfo-output",
                    str(trips),
                    "--tripinfo-output.write-unfinished",
                    "true",
                    "--no-step-log",
                    "true",
                    "--duration-log.disable",
                    "true",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            root = ET.parse(trips).getroot()
            values = list(root.findall("tripinfo"))
            delays = [
                float(v.attrib["timeLoss"]) + float(v.attrib.get("departDelay", 0)) for v in values
            ]
            cleared = sum(float(v.attrib["arrival"]) >= 0 for v in values)
            results[policy] = {
                "greens": greens,
                "mean_delay_s": float(np.mean(delays)) if delays else 0,
                "vehicles_cleared": cleared,
                "vehicles_reported": len(values),
                "scheduled_demand": len(demand),
                "unfinished_or_not_inserted": len(demand) - cleared,
                "mean_wait_s": float(np.mean([float(v.attrib["waitingTime"]) for v in values]))
                if values
                else 0,
                "warnings": completed.stderr.strip(),
            }
        version = subprocess.run(
            [str(binaries / f"sumo{executable}"), "--version"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()[0]
    save(
        "sumo",
        {
            "scope": "Independent SUMO cross-check using matched seeded arrivals and vehicle mix. ATLAS timing selected in the portable simulator, not optimized directly in SUMO. Includes reported unfinished trips; not-inserted demand listed separately. No pedestrians or turns in this validation network.",
            "sumo_version": version,
            "seed": seed,
            "runs": results,
            "delay_reduction_pct": (
                results["baseline"]["mean_delay_s"] - results["atlas_surrogate"]["mean_delay_s"]
            )
            / max(results["baseline"]["mean_delay_s"], 1e-8)
            * 100,
        },
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    try:
        main(parser.parse_args().seed)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr or str(exc)) from exc
