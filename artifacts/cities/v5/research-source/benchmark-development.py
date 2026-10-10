"""Resumable, independently paired SUMO portfolio study with a pre-final freeze."""

import argparse
import copy
import gzip
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
from atlas import config
from atlas.city_data_v4 import stamp
from atlas.control_v4 import NetworkConfig
from atlas.control_v5 import ControllerPortfolio, PortfolioConfig
from atlas.evaluation.network_v4_runtime import run_network
from atlas.learned_control_v4 import CooperativeQController, SharedQ

PROTOCOL = config.ROOT / "docs/control-v5-protocol.json"
SOURCE_PATHS = [
    "backend/atlas/control_v5.py",
    "backend/atlas/control_v4.py",
    "backend/atlas/evaluation/network_v4.py",
    "backend/atlas/evaluation/network_v4_runtime.py",
    "backend/atlas/learned_control_v4.py",
    "docs/control-v5-protocol.json",
    "artifacts/cities/v4/cooperative-q-policies.json",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def scenario(city, case, output):
    source = config.ROOT / "datasets/cities" / city
    manifest = json.loads((source / "manifest.json").read_text())
    route_file = next(p for p in source.glob("routes-*.xml") if sha(p) == manifest["routes_sha256"])
    if case not in {"low", "high", "shift"}:
        return source
    destination = output / "scenarios" / city / case
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "network.net.xml").write_bytes((source / "network.net.xml").read_bytes())
    tree = ET.parse(route_file).getroot()
    generated = ET.Element("routes")
    index = 0
    for child in tree:
        if child.tag != "vehicle":
            generated.append(copy.deepcopy(child))
            continue
        if case == "low" and index % 2:
            index += 1
            continue
        value = copy.deepcopy(child)
        if case == "shift":
            depart = float(value.attrib["depart"])
            value.set("depart", str(int(depart / 60) * 60 + (depart % 60) / 6))
        generated.append(value)
        if case == "high":
            duplicate = copy.deepcopy(child)
            duplicate.set("id", child.attrib["id"] + "-v5-high")
            duplicate.set("depart", str(float(child.attrib["depart"]) + 1.5))
            generated.append(duplicate)
        index += 1
    generated[:] = sorted(generated, key=lambda c: float(c.attrib.get("depart", -1)))
    path = destination / "routes-v5.xml"
    ET.ElementTree(generated).write(path, encoding="utf-8", xml_declaration=True)
    manifest.update(
        routes_sha256=sha(path),
        demand_case=case,
        demand_assumption="Assumed route scenarios, not calibrated municipal demand",
    )
    write(destination / "manifest.json", manifest)
    return destination


def paired_ratios(rows, candidate, baseline="max_pressure"):
    selected = {(r["city"], r["case"], r["seed"]): r for r in rows if r["candidate"] == candidate}
    base = {(r["city"], r["case"], r["seed"]): r for r in rows if r["candidate"] == baseline}
    if set(selected) != set(base):
        raise ValueError("Incomplete paired cohort")
    result = {}
    for key, row in selected.items():
        other = base[key]
        for field in ("network_sha256", "routes_sha256", "initial_states", "duration", "scenario"):
            if row[field] != other[field]:
                raise ValueError("Mismatched paired simulation inputs")
        delay = other["metrics"]["mean_delay_s"]
        if delay <= 0:
            raise ValueError("Undefined relative delay with nonpositive baseline")
        result[key] = row["metrics"]["mean_delay_s"] / delay
    return result


def freeze(output, protocol):
    rows = [
        r
        for city in protocol["cities"]
        for r in json.loads((output / f"validation-{city}.json").read_text())["runs"]
    ]
    choices = []
    expected = (
        len(protocol["cities"]) * len(protocol["final_cases"]) * len(protocol["validation_seeds"])
    )
    for threshold in protocol["candidate_congestion_thresholds"]:
        name = f"portfolio_{threshold}"
        ratios = paired_ratios(rows, name)
        if len(ratios) != expected:
            raise ValueError("Validation cohort is incomplete")
        cells = defaultdict_ratios(ratios)
        choices.append(
            {
                "candidate": name,
                "threshold": threshold,
                "worst_city_case_mean_ratio": max(float(np.mean(v)) for v in cells.values()),
                "mean_paired_delay_ratio": float(np.mean(list(ratios.values()))),
            }
        )
    selected = min(
        choices, key=lambda c: (c["worst_city_case_mean_ratio"], c["mean_paired_delay_ratio"])
    )
    value = {
        "schema_version": "atlas-controller-frozen-5.0",
        "frozen_at": stamp(),
        "frozen_before_final": True,
        "selected": selected,
        "validation_candidates": choices,
        "protocol_sha256": sha(PROTOCOL),
        "evaluator_sha256": sha(__file__),
        "source_sha256": {p: sha(config.ROOT / p) for p in SOURCE_PATHS},
        "validation_sha256": {
            city: sha(output / f"validation-{city}.json") for city in protocol["cities"]
        },
        "production_promoted": False,
    }
    write(output / "frozen.json", value)
    print("Frozen", selected, flush=True)


def defaultdict_ratios(values):
    cells = {}
    for (city, case, _), value in values.items():
        cells.setdefault((city, case), []).append(value)
    return cells


def execute(args, protocol):
    output = args.output
    cohort = output / f"{args.stage}-{args.city}.json"
    payload = (
        json.loads(cohort.read_text())
        if cohort.exists()
        else {
            "schema_version": "atlas-control-cohort-5.0",
            "stage": args.stage,
            "city": args.city,
            "protocol_sha256": sha(PROTOCOL),
            "scope": protocol["scope"],
            "runs": [],
            "failures": [],
        }
    )
    if payload["protocol_sha256"] != sha(PROTOCOL):
        raise ValueError("Cannot resume under changed protocol")
    if args.stage == "final":
        frozen = json.loads((output / "frozen.json").read_text())
        if (
            not frozen["frozen_before_final"]
            or frozen["protocol_sha256"] != sha(PROTOCOL)
            or frozen["evaluator_sha256"] != sha(__file__)
        ):
            raise ValueError("Final evaluator/protocol differs from pre-final freeze")
        for path, digest in frozen["source_sha256"].items():
            if sha(config.ROOT / path) != digest:
                raise ValueError("Frozen source changed: " + path)
        candidates = [*protocol["baselines"], frozen["selected"]["candidate"]]
    else:
        candidates = [
            "max_pressure",
            "cached_original",
            *(f"portfolio_{t}" for t in protocol["candidate_congestion_thresholds"]),
        ]
    cases = (
        protocol["development_cases"] if args.stage == "development" else protocol["final_cases"]
    )
    seeds = protocol[args.stage + "_seeds"]
    done = {(r["case"], r["seed"], r["candidate"]) for r in payload["runs"]}
    policies = json.loads((config.ARTIFACTS / "cities/v4/cooperative-q-policies.json").read_text())
    learned = next(r for r in policies["rotations"] if r["held_out_city"] == args.city)
    for case in cases:
        root = scenario(args.city, case, output)
        for seed in seeds:
            for candidate in candidates:
                if (case, seed, candidate) in done:
                    continue
                factory, source, settings = None, None, None
                if candidate.startswith("portfolio_"):
                    settings = PortfolioConfig(
                        congestion_threshold=float(candidate.split("_")[1]),
                        **protocol["fixed_settings"],
                    )
                    factory = lambda moves, profile=settings: ControllerPortfolio(moves, profile)
                    source = config.ROOT / "backend/atlas/control_v5.py"
                elif candidate == "cooperative_q":
                    shared = SharedQ(learned["table"], training=False)
                    factory = lambda moves, learner=shared: CooperativeQController(moves, learner)
                    source = config.ROOT / "backend/atlas/learned_control_v4.py"
                policy = (
                    "learned_mpc"
                    if factory
                    else "network_mpc"
                    if candidate == "cached_original"
                    else candidate
                )
                actual_scenario = (
                    "lane_closure"
                    if case == "incident"
                    else "sensor_outage"
                    if case == "outage"
                    else "nominal"
                )
                try:
                    result = run_network(
                        args.city,
                        policy,
                        seed,
                        protocol["duration_seconds"],
                        root=root,
                        scenario=actual_scenario,
                        candidate_settings=NetworkConfig(),
                        controller_factory=factory,
                        controller_source=source,
                    )
                    result.update(
                        candidate=candidate,
                        case=case,
                        stage=args.stage,
                        portfolio_settings=asdict(settings) if settings else None,
                    )
                    raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
                    archive = (
                        output
                        / "episodes"
                        / f"{args.stage}-{args.city}-{case}-{seed}-{candidate}.json.gz"
                    )
                    archive.parent.mkdir(parents=True, exist_ok=True)
                    archive.write_bytes(gzip.compress(raw, mtime=0))
                    summary = {k: v for k, v in result.items() if k not in {"trace", "decisions"}}
                    summary.update(
                        raw_archive=str(archive.relative_to(output)),
                        archive_sha256=sha(archive),
                        raw_sha256=hashlib.sha256(raw).hexdigest(),
                    )
                    payload["runs"].append(summary)
                    print(
                        args.stage,
                        args.city,
                        case,
                        seed,
                        candidate,
                        round(result["metrics"]["mean_delay_s"], 3),
                        flush=True,
                    )
                except Exception as exc:
                    payload["failures"].append(
                        {
                            "case": case,
                            "seed": seed,
                            "candidate": candidate,
                            "error_type": type(exc).__name__,
                            "reason": str(exc),
                        }
                    )
                    print("FAILED", args.city, case, seed, candidate, str(exc), flush=True)
                write(cohort, payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage", choices=["development", "validation", "freeze", "final"], required=True
    )
    parser.add_argument("--city")
    parser.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=4)
    parser.add_argument("--output", type=Path, default=config.DATA / "control-v5")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    if args.city and args.city not in protocol["cities"]:
        raise ValueError("Unsupported city")
    if args.stage == "freeze":
        freeze(args.output, protocol)
    elif args.city:
        execute(args, protocol)
    else:

        def child(city):
            return subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "--stage",
                    args.stage,
                    "--city",
                    city,
                    "--output",
                    str(args.output),
                ],
                check=True,
            )

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(child, protocol["cities"]))


if __name__ == "__main__":
    main()
