"""Algorithm microbenchmark on declared synthetic states, not road performance."""

import json
import time

import numpy as np
import psutil
from atlas import config
from atlas.control import FeedbackController, SignalMachine
from atlas.control_v2 import RiskConfig, RiskController, SafetyGate
from atlas.signal_runtime import selected_profile


def main():
    rng = np.random.default_rng(90210)
    moves = [[(f"in-{i}", f"out-{i}")] for i in range(8)]
    states = ["r" * i + "G" + "r" * (7 - i) for i in range(8)]
    process = psutil.Process()
    outcomes = []
    for label in ("frozen_mpc", "risk_mpc"):
        rng = np.random.default_rng(90210)
        controller = (
            FeedbackController(selected_profile(), moves)
            if label == "frozen_mpc"
            else RiskController(moves, RiskConfig())
        )
        latencies, cpu, rss = [], [], []
        cpu_started = process.cpu_times()
        batch_started = time.perf_counter()
        for t in range(100):
            lanes = {}
            for i in range(8):
                count = int(rng.integers(0, 30))
                lanes[f"in-{i}"] = {
                    "queue": count,
                    "vehicles": count,
                    "capacity": 40,
                    "arrival_rate": 0.1,
                    "starvation": 20,
                    "waiting": 0,
                }
                lanes[f"out-{i}"] = {
                    "queue": 0,
                    "vehicles": 5,
                    "capacity": 40,
                    "arrival_rate": 0,
                    "starvation": 0,
                    "waiting": 0,
                }
            gate = SignalMachine(states) if label == "frozen_mpc" else SafetyGate(states)
            start = time.perf_counter()
            controller.decide(20 + t * 3, gate, lanes)
            latencies.append((time.perf_counter() - start) * 1000)
            if (t + 1) % 20 == 0:
                observed = process.cpu_times()
                elapsed = time.perf_counter() - batch_started
                cpu.append(
                    100
                    * (observed.user + observed.system - cpu_started.user - cpu_started.system)
                    / elapsed
                )
                cpu_started, batch_started = observed, time.perf_counter()
            rss.append(process.memory_info().rss / 1024**2)
        outcomes.append(
            {
                "controller": label,
                "samples": 100,
                "latency_ms_p50": float(np.percentile(latencies, 50)),
                "latency_ms_p95": float(np.percentile(latencies, 95)),
                "process_cpu_percent_p50": float(np.percentile(cpu, 50)),
                "process_cpu_percent_p95": float(np.percentile(cpu, 95)),
                "process_rss_mib_p50": float(np.percentile(rss, 50)),
                "process_rss_mib_p95": float(np.percentile(rss, 95)),
            }
        )
    (config.ARTIFACTS / "cities/performance.json").write_text(
        json.dumps(
            {
                "scope": "Native CPU microbenchmark, 8-movement synthetic states; process RSS includes Python dependencies; not camera FPS or a full deployment load test",
                "hardware": {
                    "logical_cpus": psutil.cpu_count(),
                    "memory_gib": psutil.virtual_memory().total / 1024**3,
                },
                "results": outcomes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(outcomes)


if __name__ == "__main__":
    main()
