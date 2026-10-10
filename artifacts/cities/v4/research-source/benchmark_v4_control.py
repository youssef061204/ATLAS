"""Resumable paired SUMO study. Never substitutes predictions for actual episodes."""

import argparse
import copy
import gzip
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
from atlas import config
from atlas.cities import now
from atlas.city_network import sha
from atlas.control_v4 import NetworkConfig
from atlas.evaluation.network_v4 import run_network

CITIES = ["toronto", "london", "seattle", "austin", "calgary"]
CANDIDATES = {
    "cached_original": NetworkConfig(),
    "adaptive_queue": NetworkConfig(adaptive_queue=True),
    "adaptive_queue_running0": NetworkConfig(adaptive_queue=True, running_weight=0),
    "running0": NetworkConfig(running_weight=0),
    "running1": NetworkConfig(running_weight=1),
    "arrivals0": NetworkConfig(arrival_weight=0),
    "arrivals05": NetworkConfig(arrival_weight=0.5),
    "arrivals2": NetworkConfig(arrival_weight=2),
    "service04": NetworkConfig(service_rate=0.4),
    "queue1": NetworkConfig(queue_weight=1),
    "downstream0": NetworkConfig(downstream_weight=0),
    "network_hint": NetworkConfig(coordination_weight=1),
    "long_horizon": NetworkConfig(horizon=40, coordination_weight=1),
    "short_horizon": NetworkConfig(horizon=20, coordination_weight=1),
    "service_05": NetworkConfig(service_rate=0.5, coordination_weight=1),
    "fast_queue": NetworkConfig(service_rate=0.8, coordination_weight=1, queue_weight=0.3),
    "minimum10": NetworkConfig(min_green=10, coordination_weight=1),
    "interval3": NetworkConfig(decision_interval=3, coordination_weight=1),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", nargs="+", choices=CITIES, default=CITIES)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=41001)
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--demand-regime", choices=["nominal", "low", "high"], default="nominal")
    parser.add_argument(
        "--candidates", nargs="+", choices=list(CANDIDATES), default=list(CANDIDATES)
    )
    parser.add_argument(
        "--baselines",
        nargs="*",
        default=["fixed", "max_pressure", "original_mpc", "risk_mpc", "actuated"],
    )
    parser.add_argument(
        "--scenario", choices=["nominal", "sensor_outage", "lane_closure"], default="nominal"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-profile", type=Path)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=1)
    args = parser.parse_args()
    frozen = None
    if args.seed_start >= 43001 and args.seed_start < 44000:
        if args.frozen_profile is None:
            raise ValueError("Final seeds require a configuration frozen before evaluation")
    if args.frozen_profile is not None:
        frozen = json.loads(args.frozen_profile.read_text())
        if not frozen.get("frozen_before_final"):
            raise ValueError("Profile is not marked frozen")
        for source, checksum in frozen["source_hashes"].items():
            source_path = (
                Path(__file__)
                if source == "scripts/benchmark_v4_control.py"
                else config.ROOT / source
            )
            if sha(source_path) != checksum:
                raise ValueError("Frozen source changed: " + source)
        if (
            args.candidates != [frozen["selected_candidate"]]
            or asdict(CANDIDATES[args.candidates[0]]) != frozen["settings"]
        ):
            raise ValueError("Final candidate differs from frozen profile")
        if args.duration != frozen["duration_seconds"] or not set(
            range(args.seed_start, args.seed_start + args.seeds)
        ).issubset(frozen["final_seeds"]):
            raise ValueError("Final episode duration/seeds differ from protocol")
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.workers > 1 and len(args.cities) > 1:

        def execute(city):
            child_output = output.with_name(output.stem + "-" + city + output.suffix)
            command = [
                sys.executable,
                __file__,
                "--cities",
                city,
                "--seeds",
                str(args.seeds),
                "--seed-start",
                str(args.seed_start),
                "--duration",
                str(args.duration),
                "--candidates",
                *args.candidates,
                "--baselines",
                *args.baselines,
                "--scenario",
                args.scenario,
                "--demand-regime",
                args.demand_regime,
                "--output",
                str(child_output),
            ]
            if args.frozen_profile:
                command.extend(["--frozen-profile", str(args.frozen_profile)])
            subprocess.run(command, check=True)
            return json.loads(child_output.read_text())

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            parts = list(pool.map(execute, args.cities))
        merged = {
            **parts[0],
            "parallel_workers": args.workers,
            "timing_scope": "Matched physics, concurrent city workers on shared host; timing is not isolated production SLA",
        }
        for key in ("runs", "summaries", "failures"):
            merged[key] = [row for part in parts for row in part[key]]
        output.write_text(
            json.dumps(merged, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
        return
    payload = (
        json.loads(output.read_text())
        if output.exists()
        else {
            "schema_version": "atlas-control-v4-1",
            "split": "final_heldout"
            if frozen
            else "validation"
            if args.seed_start >= 42001
            else "development",
            "protocol_sha256": sha(args.frozen_profile) if frozen else None,
            "demand_regime": args.demand_regime,
            "recorded_at": now(),
            "scope": "Exploratory existing uncalibrated OSM corridors; generated OD, not real field savings",
            "runs": [],
            "failures": [],
            "summaries": [],
        }
    )
    if payload.get("demand_regime", args.demand_regime) != args.demand_regime:
        raise ValueError("Cannot resume an artifact across demand regimes")
    done = {(r["city"], r["candidate"], r["seed"], r["scenario"]) for r in payload["runs"]}
    for city in args.cities:
        scenario_root = None
        if args.demand_regime != "nominal":
            source_root = config.ROOT / "datasets/cities" / city
            manifest = json.loads((source_root / "manifest.json").read_text())
            route_source = next(
                p for p in source_root.glob("routes-*.xml") if sha(p) == manifest["routes_sha256"]
            )
            scenario_root = config.ROOT / "datasets/control-v4-demand" / city / args.demand_regime
            scenario_root.mkdir(parents=True, exist_ok=True)
            (scenario_root / "network.net.xml").write_bytes(
                (source_root / "network.net.xml").read_bytes()
            )
            tree = ET.parse(route_source).getroot()
            generated = ET.Element("routes")
            vehicle_index = 0
            for child in tree:
                if child.tag != "vehicle":
                    generated.append(copy.deepcopy(child))
                elif args.demand_regime == "low":
                    if vehicle_index % 2 == 0:
                        generated.append(copy.deepcopy(child))
                else:
                    generated.append(copy.deepcopy(child))
                    duplicate = copy.deepcopy(child)
                    duplicate.set("id", child.attrib["id"] + "-high-copy")
                    duplicate.set("depart", str(float(child.attrib["depart"]) + 1.5))
                    generated.append(duplicate)
                if child.tag == "vehicle":
                    vehicle_index += 1
            generated[:] = sorted(
                generated, key=lambda child: float(child.attrib.get("depart", -1))
            )
            path = scenario_root / "routes-v4.xml"
            ET.ElementTree(generated).write(path, encoding="utf-8", xml_declaration=True)
            manifest["routes_sha256"] = sha(path)
            manifest["demand_regime"] = args.demand_regime
            manifest["demand_assumption"] = (
                "Deterministic half/full/double generated OD demand; not calibrated municipal demand"
            )
            (scenario_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            for candidate in [*args.baselines, *args.candidates]:
                if (city, candidate, seed, args.scenario) in done:
                    continue
                try:
                    result = run_network(
                        city,
                        "network_mpc" if candidate in CANDIDATES else candidate,
                        seed,
                        args.duration,
                        scenario=args.scenario,
                        root=scenario_root,
                        candidate_settings=CANDIDATES.get(candidate, NetworkConfig()),
                    )
                    result["candidate"] = candidate
                    result["demand_regime"] = args.demand_regime
                    # Lossless original episodes remain independently inspectable.
                    archive = (
                        output.parent
                        / f"{output.stem}-{city}-{candidate}-{seed}-{args.scenario}.json.gz"
                    )
                    with gzip.open(archive, "wt", encoding="utf-8") as f:
                        json.dump(result, f, separators=(",", ":"), allow_nan=False)
                    result["raw_archive"] = archive.name
                    result["trace"] = (
                        [
                            {
                                k: v
                                for k, v in frame.items()
                                if k not in {"lane_observations", "movements"}
                            }
                            for frame in result["trace"]
                        ]
                        if seed == args.seed_start
                        else []
                    )
                    result["decisions"] = result["decisions"] if seed == args.seed_start else []
                    payload["runs"].append(result)
                except Exception as exc:
                    payload["failures"].append(
                        dict(
                            city=city,
                            candidate=candidate,
                            seed=seed,
                            scenario=args.scenario,
                            demand_regime=args.demand_regime,
                            reason=repr(exc),
                        )
                    )
                    print(city, candidate, seed, "FAILED", repr(exc), flush=True)
                output.write_text(
                    json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8"
                )
    summaries = []
    for city in CITIES:
        for candidate in [*args.baselines, *args.candidates]:
            rows = [r for r in payload["runs"] if r["city"] == city and r["candidate"] == candidate]
            if not rows:
                continue
            metrics = {
                key: float(np.mean([r["metrics"][key] for r in rows]))
                for key in rows[0]["metrics"]
                if isinstance(rows[0]["metrics"][key], (int, float))
            }
            comparisons = []
            for baseline in ("fixed", "max_pressure", "original_mpc"):
                base = {
                    r["seed"]: r
                    for r in payload["runs"]
                    if r["city"] == city and r["candidate"] == baseline
                }
                differences = []
                for row in rows:
                    if row["seed"] not in base:
                        continue
                    other = base[row["seed"]]
                    keys = (
                        "network_sha256",
                        "routes_sha256",
                        "initial_states",
                        "duration",
                        "scenario",
                    )
                    if any(row[k] != other[k] for k in keys):
                        raise ValueError("Unpaired experiment inputs")
                    delay = other["metrics"]["mean_delay_s"]
                    differences.append(100 * (delay - row["metrics"]["mean_delay_s"]) / delay)
                if differences:
                    values = np.array(differences)
                    rng = np.random.default_rng(44)
                    samples = values[rng.integers(0, len(values), (20000, len(values)))].mean(
                        axis=1
                    )
                    comparisons.append(
                        dict(
                            baseline=baseline,
                            n=len(values),
                            mean_paired_reduction_pct=float(values.mean()),
                            ci95=list(map(float, np.percentile(samples, [2.5, 97.5]))),
                            improvements=int((values > 0).sum()),
                        )
                    )
            summaries.append(
                dict(
                    city=city,
                    candidate=candidate,
                    seeds=len(rows),
                    metrics=metrics,
                    comparisons=comparisons,
                )
            )
    payload["summaries"] = summaries
    payload["candidate_settings"] = {k: asdict(v) for k, v in CANDIDATES.items()}
    output.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    for s in summaries:
        print(
            s["city"],
            s["candidate"],
            round(s["metrics"]["mean_delay_s"], 3),
            round(s["metrics"]["decision_ms_p95"], 4),
            flush=True,
        )


if __name__ == "__main__":
    main()
