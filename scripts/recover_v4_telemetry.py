"""Recover a failed serialization attempt without changing simulator/controller logic.

Runs in an isolated research process. Non-finite geographic replay coordinates become
explicitly unavailable with their exact paths retained. Non-finite metrics are refused.
The frozen harness and controllers retain their original bytes and traffic decisions.
"""

import gzip
import hashlib
import json
import math
import types
from pathlib import Path

from atlas import config
from atlas.evaluation import network_v4


def main():
    frozen = json.loads((config.ROOT / "docs/control-v4-frozen.json").read_text())
    for name, expected in frozen["source_hashes"].items():
        path = config.ROOT / name
        if name == "scripts/benchmark_v4_control.py":
            path = config.DATA / "benchmark_v4_control-final.py"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    unavailable = {}

    def sanitize(value, path=""):
        if isinstance(value, float) and not math.isfinite(value):
            if path.startswith("metrics"):
                raise ValueError(f"Measured metric non-finite: {path}")
            if not path.startswith("trace"):
                raise ValueError(f"Unexpected non-finite field: {path}")
            unavailable[path] = repr(value)
            return None
        if isinstance(value, dict):
            return {
                key: sanitize(item, f"{path}.{key}" if path else key) for key, item in value.items()
            }
        if isinstance(value, list):
            return [sanitize(item, f"{path}[{index}]") for index, item in enumerate(value)]
        return value

    def finite_dump(value, **kwargs):
        return json.dumps(sanitize(value), **kwargs)

    original = network_v4.json
    network_v4.json = types.SimpleNamespace(loads=json.loads, dumps=finite_dump)
    try:
        result = network_v4.run_network(
            "austin",
            "actuated",
            43002,
            300,
            root=config.ROOT / "datasets/control-v4-demand/austin/high",
        )
    finally:
        network_v4.json = original
    result = sanitize(result)
    assert unavailable, "Recovery needs a reproduced non-finite replay field"
    result.update(candidate="actuated", demand_regime="high")
    result["telemetry_recovery"] = {
        "serialization_adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "unavailable_fields": unavailable,
        "scope": "Exact frozen SUMO/controller execution; non-finite replay fields represented as unavailable. Metrics are finite and unchanged by serialization.",
    }
    path = config.DATA / "control-v4-heldout-high-austin-austin-actuated-43002-nominal.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as out:
        json.dump(result, out, separators=(",", ":"), allow_nan=False)
    result.update(raw_archive=path.name, trace=[], decisions=[])
    shard_path = config.DATA / "control-v4-heldout-high-austin.json"
    shard = json.loads(shard_path.read_text())
    assert not any(row["candidate"] == "actuated" and row["seed"] == 43002 for row in shard["runs"])
    shard["runs"].append(result)
    matched = [
        row for row in shard["failures"] if row["candidate"] == "actuated" and row["seed"] == 43002
    ]
    assert len(matched) == 1
    shard["attempt_failures"] = [*shard.get("attempt_failures", []), *matched]
    shard["failures"] = [row for row in shard["failures"] if row not in matched]
    shard_path.write_text(json.dumps(shard, separators=(",", ":"), allow_nan=False))
    (config.DATA / "control-v4-telemetry-recovery.json").write_text(
        json.dumps({"prior_failed_attempts": matched, **result["telemetry_recovery"]}, indent=2)
    )
    print("Recovered actual episode; unavailable replay fields:", unavailable)


if __name__ == "__main__":
    main()
