"""Actual five rotations of cooperative Q training, followed by frozen zero-shot SUMO."""

import argparse
import gzip
import json
import os
import time
from pathlib import Path

from atlas.cities import now
from atlas.city_network import sha
from atlas.evaluation.network_v4 import run_network
from atlas.learned_control_v4 import CooperativeQController, SharedQ


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("train", "test"), required=True)
    args = parser.parse_args()
    protocol_path = Path("docs/learned-control-v4-protocol.json")
    protocol = json.loads(protocol_path.read_text())
    output = Path("data/learned-control-v4")
    output.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(os.environ.get("ATLAS_V4_ARTIFACTS", "artifacts/cities/v4"))
    artifact_root.mkdir(parents=True, exist_ok=True)
    model_path = artifact_root / "cooperative-q-policies.json"
    if args.stage == "train":
        rotations = []
        for heldout in protocol["cities"]:
            learner = SharedQ(training=True)
            episodes = []
            started = time.perf_counter()
            for seed in protocol["training"]["seeds"]:
                for city in protocol["cities"]:
                    if city == heldout:
                        continue
                    result = run_network(
                        city,
                        "marl",
                        seed,
                        duration=protocol["training"]["duration_seconds"],
                        controller_factory=lambda moves, shared=learner: CooperativeQController(
                            moves, shared
                        ),
                        controller_source=Path("backend/atlas/learned_control_v4.py"),
                    )
                    episodes.append(
                        {
                            "city": city,
                            "seed": seed,
                            "metrics": result["metrics"],
                            "network_sha256": result["network_sha256"],
                            "routes_sha256": result["routes_sha256"],
                        }
                    )
                    target = output / f"train-{heldout}-{city}-{seed}.json.gz"
                    target.write_bytes(
                        gzip.compress(json.dumps(result, allow_nan=False).encode(), mtime=0)
                    )
            rotations.append(
                {
                    "held_out_city": heldout,
                    "trained_cities": [c for c in protocol["cities"] if c != heldout],
                    "table": learner.table,
                    "updates": learner.updates,
                    "training_seconds": time.perf_counter() - started,
                    "training_episodes": episodes,
                    "training_source_sha256": sha("backend/atlas/learned_control_v4.py"),
                    "harness_sha256": sha("backend/atlas/evaluation/network_v4.py"),
                }
            )
            model_path.write_text(
                json.dumps(
                    {
                        "experiment_id": protocol["experiment_id"],
                        "registered_protocol_sha256": sha(protocol_path),
                        "recorded_at": now(),
                        "rotations": rotations,
                        "frozen_for_evaluation": False,
                    },
                    indent=2,
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
        value = json.loads(model_path.read_text())
        value["frozen_for_evaluation"] = True
        model_path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        print("All five actual four-city training rotations frozen", sha(model_path), flush=True)
    else:
        models = json.loads(model_path.read_text())
        if not models["frozen_for_evaluation"] or models["registered_protocol_sha256"] != sha(
            protocol_path
        ):
            raise ValueError("Unfrozen or changed training protocol")
        runs, failures = [], []
        result_path = artifact_root / "cooperative-q-results.json"
        for rotation in models["rotations"]:
            city = rotation["held_out_city"]
            if rotation["training_source_sha256"] != sha("backend/atlas/learned_control_v4.py"):
                raise ValueError("Frozen learned source changed")
            for seed in protocol["evaluation"]["seeds"]:
                learner = SharedQ(rotation["table"], training=False)
                try:
                    result = run_network(
                        city,
                        "marl",
                        seed,
                        duration=protocol["evaluation"]["duration_seconds"],
                        controller_factory=lambda moves, shared=learner: CooperativeQController(
                            moves, shared
                        ),
                        controller_source=Path("backend/atlas/learned_control_v4.py"),
                    )
                    archive = output / f"test-{city}-{seed}.json.gz"
                    archive.write_bytes(
                        gzip.compress(json.dumps(result, allow_nan=False).encode(), mtime=0)
                    )
                    runs.append(
                        {
                            "city": city,
                            "seed": seed,
                            "policy": "cooperative_q_zero_shot",
                            "metrics": result["metrics"],
                            "network_sha256": result["network_sha256"],
                            "routes_sha256": result["routes_sha256"],
                            "harness_sha256": result["harness_sha256"],
                            "archive": archive.name,
                            "archive_sha256": sha(archive),
                            "decisions": result["decisions"][:20],
                            "target_city_fit_episodes": 0,
                        }
                    )
                except Exception as exc:
                    failures.append({"city": city, "seed": seed, "error": str(exc)})
                result_path.write_text(
                    json.dumps(
                        {
                            "experiment_id": protocol["experiment_id"],
                            "recorded_at": now(),
                            "policy_sha256": sha(model_path),
                            "protocol_sha256": sha(protocol_path),
                            "runs": runs,
                            "failures": failures,
                            "limitations": protocol["limitations"],
                            "promoted": False,
                        },
                        indent=2,
                        allow_nan=False,
                    ),
                    encoding="utf-8",
                )


if __name__ == "__main__":
    main()
