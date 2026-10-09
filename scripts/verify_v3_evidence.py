"""Verify published experiment provenance and paired inputs without rerunning models."""

import gzip
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON value in {path}: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def verify_pair(pair):
    a, b = pair["runs"]
    for key in (
        "city",
        "seed",
        "duration",
        "network_sha256",
        "routes_sha256",
        "initial_states",
        "scenario",
    ):
        assert a[key] == b[key], (pair["id"], key)
    assert a["policy"] == pair["comparison"]["baseline"]
    assert b["policy"] == "risk_mpc"
    assert (
        abs(
            pair["comparison"]["mean_delay_difference_s"]
            - (a["metrics"]["mean_delay_s"] - b["metrics"]["mean_delay_s"])
        )
        < 1e-10
    )
    assert not pair["hardware_actuation"]


def main():
    root = Path("artifacts/cities")
    files = list(root.rglob("*.json"))
    for path in files:
        read(path)
    archives = read(root / "evidence-archives.json")["archives"]
    total = 0
    for archive in archives:
        compressed = (root / archive["published"]).read_bytes()
        raw = gzip.decompress(compressed)
        assert digest(compressed) == archive["archive_sha256"]
        assert digest(raw) == archive["uncompressed_sha256"]
        assert len(raw) == archive["uncompressed_bytes"]
        assert len(compressed) == archive["compressed_bytes"]
        total += len(raw)
    protocol = read("docs/atlas-2-protocol.json")
    for name, expected in protocol["frozen_source_sha256"].items():
        assert digest(Path(name).read_bytes()) == expected, name
    neural = read(root / "graph-forecast.json")
    assert (
        digest(Path("docs/graph-forecast-protocol.json").read_bytes()) == neural["protocol_sha256"]
    )
    for filename, key in (
        ("frozen_model_source", "model_source_sha256"),
        ("frozen_evaluation_source", "evaluation_source_sha256"),
    ):
        assert digest((root / neural[filename]).read_bytes()) == neural[key]
    classical = read(root / "forecast-v3.json")
    assert (
        digest(Path("docs/forecast-v3-protocol.json").read_bytes()) == classical["protocol_sha256"]
    )
    assert (
        digest((root / classical["frozen_feature_source"]).read_bytes())
        == classical["source_sha256"]
    )
    pairs = [
        read(root / "toronto-golden-path.json"),
        read(root / "toronto-golden-path-initial.json"),
    ]
    smoke = read(root / "city-intelligence-smoke.json")
    observations = 0
    for record in smoke["records"]:
        for attempt in record["attempts"]:
            if "context" in attempt:
                context = attempt["context"]
                assert context["city"] == record["city"]
                assert (
                    context["camera"]["id"]
                    == context["observation"]["camera_id"]
                    == attempt["camera_id"]
                )
                assert "image_data_url" not in context
                observations += 1
                if attempt["state"] == "zero_motor_observation_not_simulated":
                    assert context["estimated_state"]["mean"] == 0 and "experiment" not in attempt
            if "experiment" in attempt:
                pair = attempt["experiment"]
                assert pair["city"] == record["city"]
                assert pair["observation"]["id"] == attempt["context"]["observation"]["id"]
                pairs.append(pair)
    for pair in pairs:
        verify_pair(pair)
    print(
        f"Verified {len(files)} finite JSON files, {len(archives)} lossless archives ({total:,} original bytes), frozen protocols/sources, {len(pairs)} matched pairs and {observations} additional official observations"
    )


if __name__ == "__main__":
    main()
