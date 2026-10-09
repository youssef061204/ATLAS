"""Small real OSM corridors with explicitly assumed, independently routed demand."""

import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas import config
from atlas.cities import FeedClient, city_configs, now


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def binary(name):
    import sumo

    return str(Path(sumo.SUMO_HOME) / "bin" / (name + (".exe" if os.name == "nt" else "")))


def checked(command, directory):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (directory / (Path(command[0]).stem + ".log")).write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed; inspect {directory}")


def generate(city, seed=12001, duration=600, period=4, download=False):
    import sumo
    import sumolib

    if duration < 60 or duration > 3600 or period <= 0:
        raise ValueError("Use bounded research scenario settings")
    s = city_configs()[city]
    directory = config.ROOT / "datasets/cities" / city
    directory.mkdir(parents=True, exist_ok=True)
    osm = directory / "source.osm.xml"
    bbox = ",".join(map(str, s["bbox"]))
    url = "https://api.openstreetmap.org/api/0.6/map"
    if download or not osm.exists():
        client = FeedClient(min_interval=1)
        try:
            body, _ = client.read(
                url, ["api.openstreetmap.org"], {"bbox": bbox}, max_bytes=40_000_000
            )
        finally:
            client.close()
        if ET.fromstring(body).tag != "osm":
            raise ValueError("Invalid OSM source")
        osm.write_bytes(body)
        (directory / "source.json").write_text(
            json.dumps(
                {
                    "source": url,
                    "bbox": s["bbox"],
                    "downloaded_at": now(),
                    "sha256": sha(osm),
                    "license": "ODbL 1.0",
                    "attribution": "© OpenStreetMap contributors",
                    "terms": "https://www.openstreetmap.org/copyright",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    net = directory / "network.net.xml"
    command = [
        binary("netconvert"),
        "--osm-files",
        str(osm),
        "--output-file",
        str(net),
        "--geometry.remove",
        "true",
        "--remove-edges.isolated",
        "true",
        "--keep-edges.by-vclass",
        "passenger",
        "--tls.guess",
        "true",
        "--tls.default-type",
        "static",
        "--tls.yellow.time",
        "3",
        "--tls.allred.time",
        "2",
        "--no-turnarounds",
        "true",
    ]
    if s["left_hand"]:
        command += ["--lefthand", "true"]
    checked(command, directory)
    network = sumolib.net.readNet(str(net), withPrograms=True)
    if not network.getEdges():
        raise ValueError("No drivable roads in imported region")
    trips = directory / f"trips-{seed}-{duration}-{period}.xml"
    routes = directory / f"routes-{seed}-{duration}-{period}.xml"
    checked(
        [
            sys.executable,
            str(Path(sumo.SUMO_HOME) / "tools/randomTrips.py"),
            "-n",
            str(net),
            "-o",
            str(trips),
            "-r",
            str(routes),
            "--seed",
            str(seed),
            "--begin",
            "0",
            "--end",
            str(duration),
            "--period",
            str(period),
            "--min-distance",
            "100",
            "--validate",
            "--vehicle-class",
            "passenger",
        ],
        directory,
    )
    if not routes.exists() or not ET.parse(routes).getroot().findall("vehicle"):
        raise ValueError("No valid routed trips in imported region")
    simulation = directory / "scenario.sumocfg"
    simulation.write_text(
        f'<configuration><input><net-file value="{net.name}"/><route-files value="{routes.name}"/></input><time><end value="{duration}"/></time></configuration>',
        encoding="utf-8",
    )
    signals, roads = [], []
    for tls in network.getTrafficLights():
        node = (
            network.getNode(tls.getID())
            if tls.getID() in {n.getID() for n in network.getNodes()}
            else None
        )
        coord = network.convertXY2LonLat(*node.getCoord()) if node else None
        signals.append(
            {
                "id": tls.getID(),
                "lon": coord[0] if coord else None,
                "lat": coord[1] if coord else None,
            }
        )
    for edge in network.getEdges():
        roads.append(
            {
                "id": edge.getID(),
                "lanes": edge.getLaneNumber(),
                "speed_limit_mps": edge.getSpeed(),
                "coordinates": [
                    list(network.convertXY2LonLat(*point)) for point in edge.getShape()
                ],
            }
        )
    source = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    manifest = {
        "city": city,
        "created_at": now(),
        "mode": "exploratory_osm_simulation",
        "network_sha256": sha(net),
        "routes_sha256": sha(routes),
        "source": source,
        "netconvert_command": command,
        "sumo_version": subprocess.check_output(
            [binary("sumo"), "--version"], text=True
        ).splitlines()[0],
        "signals": signals,
        "roads": roads,
        "seed": seed,
        "duration": duration,
        "period": period,
        "scheduled": len(ET.parse(routes).getroot().findall("vehicle")),
        "calibration": {
            "status": "uncalibrated",
            "demand": "SUMO randomTrips synthetic assumed OD; not camera-derived demand",
            "signal_timings": "Generated SUMO research phases; not municipal plans",
            "gaps": [
                "Independent counts",
                "Turn ratios",
                "Signal timing and pedestrian surveys",
                "Transit occupancy",
                "Validation holdout",
            ],
        },
    }
    directory.joinpath("manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8"
    )
    return manifest
