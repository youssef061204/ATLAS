"""Matched causal lane snapshots, isolated original/cached decision profiling."""

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import psutil
from atlas.cities import now
from atlas.city_network import sha
from atlas.control import FeedbackController
from atlas.control_v2 import SafetyGate, SafetyProfile
from atlas.control_v4 import NetworkController
from atlas.signal_runtime import selected_profile


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--output", type=Path, default=Path("artifacts/cities/v4/controller-profile.json")
    )
    args = p.parse_args()
    rng = np.random.default_rng(440)
    moves = [[(f"a{i}", f"b{i}"), (f"a{(i + 1) % 8}", f"b{(i + 1) % 8}")] for i in range(8)]
    states = ["r" * i + "G" + "r" * (7 - i) for i in range(8)]
    observations = [
        {
            a: dict(
                queue=float(rng.integers(0, 10)),
                vehicles=12.0,
                capacity=30.0,
                arrival_rate=float(rng.uniform(0, 0.5)),
                starvation=float(rng.integers(0, 120)),
                waiting=0.0,
            )
            for a in [f"{letter}{i}" for letter in "ab" for i in range(8)]
        }
        for _ in range(1000)
    ]
    policies = {
        "original_mpc": FeedbackController(selected_profile(), moves),
        "cached_mpc": NetworkController(moves),
    }
    samples, actions, peak = {k: [] for k in policies}, {k: [] for k in policies}, {}
    process = psutil.Process()
    for index, lanes in enumerate(observations):
        for name in list(policies) if index % 2 else list(reversed(policies)):
            controller = policies[name]
            gate = SafetyGate(states, SafetyProfile(min_green=10))
            gate.current = index % 8
            controller.last_decision = -(10**9)
            tick = time.perf_counter_ns()
            action, _ = controller.decide(12 + index % 49, gate, lanes)
            samples[name].append((time.perf_counter_ns() - tick) / 1e6)
            actions[name].append(action)
            peak[name] = max(peak.get(name, 0), process.memory_info().rss)
    result = {
        "recorded_at": now(),
        "platform": platform.platform(),
        "scope": "1000 matched synthetic eight-phase decision snapshots; interleaved host timing; not SUMO or city field effectiveness",
        "includes": "decide including topology/state/beam calculations; preconstructed controllers; no HTTP, simulator or frontend",
        "actions_match": sum(a == b for a, b in zip(*actions.values(), strict=True)),
        "samples": 1000,
        "policies": {
            k: dict(
                p50_ms=float(np.percentile(v, 50)),
                p95_ms=float(np.percentile(v, 95)),
                peak_process_rss_mib=peak[k] / 1024**2,
            )
            for k, v in samples.items()
        },
        "controller_hashes": {
            k: sha(Path("backend/atlas") / filename)
            for k, filename in [("original_mpc", "control.py"), ("cached_mpc", "control_v4.py")]
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
