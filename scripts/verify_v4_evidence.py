"""Verify published provenance, complete cohorts and lossless actual execution evidence."""

import gzip
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path("artifacts/cities/v4")
CITIES = {"toronto", "london", "seattle", "austin", "calgary"}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    def invalid(value):
        raise ValueError(f"Non-finite value in {path}: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def verify_cohort(name, final=False):
    study = read(ROOT / f"{name}.json")
    assert not study["failures"], name
    rows = study["runs"]
    if final:
        assert study["publication_status"] == "final"
        assert len(rows) == 600
        assert {r["city"] for r in rows} == CITIES
        assert {r["seed"] for r in rows} == set(range(43001, 43021))
        assert len({(r["city"], r["seed"], r["candidate"]) for r in rows}) == 600
        assert study["protocol_sha256"] == sha(Path("docs/control-v4-frozen.json").read_bytes())
        for city in CITIES:
            for seed in range(43001, 43021):
                pair = [r for r in rows if r["city"] == city and r["seed"] == seed]
                assert len(pair) == 6
                for key in (
                    "network_sha256",
                    "routes_sha256",
                    "initial_states",
                    "duration",
                    "scenario",
                ):
                    assert all(r[key] == pair[0][key] for r in pair), (city, seed, key)
                original = next(r for r in pair if r["candidate"] == "original_mpc")
                cached = next(r for r in pair if r["candidate"] == "cached_original")
                for key in ("mean_delay_s", "completed_trips", "mean_queue", "phase_switches"):
                    assert original["metrics"][key] == cached["metrics"][key], (city, seed, key)
                assert all(r["metrics"]["modeled_safety_violations"] == 0 for r in pair)
    indexed = {(r["city"], r["seed"], r["candidate"]): r for r in rows}
    members = 0
    for bundle in read(ROOT / study["evidence_index"])["bundles"]:
        compressed = (ROOT / bundle["file"]).read_bytes()
        raw = gzip.decompress(compressed)
        assert sha(compressed) == bundle["gzip_sha256"]
        assert sha(raw) == bundle["raw_sha256"]
        assert len(raw) == bundle["raw_bytes"]
        actual = [json.loads(line) for line in raw.splitlines()]
        assert len(actual) == len(bundle["members"])
        for source, member in zip(actual, bundle["members"], strict=True):
            row = indexed[(member["city"], member["seed"], member["candidate"])]
            assert source["metrics"] == row["metrics"]
        members += len(actual)
    assert members == len(rows)
    return members


def main():
    for path in ROOT.rglob("*.json"):
        read(path)
    index = read(ROOT / "data-index.json")
    assert {r["city"] for r in index["cities"]} == CITIES
    count = 0
    for row in index["cities"]:
        encoded = (ROOT / row["artifact"]).read_bytes()
        raw = gzip.decompress(encoded)
        assert sha(encoded) == row["sha256"]
        assert sha(raw) == row["uncompressed_sha256"]
        document = json.loads(raw)
        assert len(document["records"]) == row["records"]
        assert document["live_fusion"] == "prohibited_without_temporal_spatial_compatibility"
        assert all(type(r["count"]) is int and r["count"] >= 0 for r in document["records"])
        count += row["records"]
    assert count == 52679
    forecast = read(ROOT / "city-forecast.json")
    assert forecast["protocol_sha256"] == sha(
        Path("docs/city-forecast-v4-protocol.json").read_bytes()
    )
    for city in forecast["cities"]:
        data = next(row for row in index["cities"] if row["city"] == city["city"])
        assert city["data_sha256"] == data["sha256"]
        winner = min(city["models"], key=lambda r: r["validation"]["mae_count_per_native_interval"])
        assert city["validation_selected"] == winner["name"]
        assert not city["field_twin_calibrated"]
    assert {r["held_out_city"] for r in forecast["leave_one_city_out"]} == CITIES
    for row in forecast["leave_one_city_out"]:
        assert row["target_city_fit_examples"] == 0
        assert set(row["trained_cities"]) == CITIES - {row["held_out_city"]}
        assert not row["promoted"]
    for source in read(ROOT / "research-source.json")["sources"]:
        assert sha((ROOT / source["archive"]).read_bytes()) == source["sha256"]
        assert sha(Path(source["path"]).read_bytes()) == source["sha256"]
    frozen = read("docs/control-v4-frozen.json")
    for path, expected in frozen["source_hashes"].items():
        assert sha(Path(path).read_bytes()) == expected, path
    episodes = sum(verify_cohort(f"controller-{split}") for split in ("development", "validation"))
    for regime in ("nominal", "low", "high"):
        episodes += verify_cohort(f"controller-heldout-{regime}", final=True)
    policy = read(ROOT / "cooperative-q-policies.json")
    result = read(ROOT / "cooperative-q-results.json")
    assert policy["frozen_for_evaluation"] and not result["promoted"]
    assert result["policy_sha256"] == sha((ROOT / "cooperative-q-policies.json").read_bytes())
    assert not result["failures"] and len(result["runs"]) == 100
    assert len({(r["city"], r["seed"]) for r in result["runs"]}) == 100
    assert all(
        r["target_city_fit_episodes"] == 0 and r["metrics"]["modeled_safety_violations"] == 0
        for r in result["runs"]
    )
    archives = read(ROOT / "cooperative-q-archives.json")
    assert sha((ROOT / archives["archive"]).read_bytes()) == archives["sha256"]
    with zipfile.ZipFile(ROOT / archives["archive"]) as bundle:
        assert len(bundle.namelist()) == len(archives["episodes"]) == 140
        for row in archives["episodes"]:
            encoded = bundle.read(row["member"])
            assert sha(encoded) == row["sha256"]
            assert sha(gzip.decompress(encoded)) == row["uncompressed_sha256"]
    cv = read(ROOT / "perception.json")
    assert cv["protocol_sha256"] == sha(Path("docs/cv-v4-protocol.json").read_bytes())
    assert all(r["metrics"]["frames"] == 4260 for r in cv["rows"])
    assert not cv["promoted"]
    surrogate = read(ROOT / "surrogate.json")
    assert (
        sha(gzip.decompress((ROOT / "surrogate-training.json.gz").read_bytes()))
        == surrogate["training_input_sha256"]
    )
    assert not surrogate["simulator_replacement"]
    diagnostics = read(ROOT / "controller-rejected-diagnostics.json")
    assert sha((ROOT / diagnostics["archive"]).read_bytes()) == diagnostics["sha256"]
    with zipfile.ZipFile(ROOT / diagnostics["archive"]) as bundle:
        assert len(bundle.namelist()) == len(diagnostics["episodes"])
        for row in diagnostics["episodes"]:
            encoded = bundle.read(row["member"])
            assert sha(encoded) == row["sha256"]
            assert sha(gzip.decompress(encoded)) == row["raw_sha256"]
    assessment = read(ROOT / "controller-assessment.json")
    quality = read(ROOT / "measurement-quality.json")
    for name, expected in quality["source_sha256"].items():
        assert sha((ROOT / name).read_bytes()) == expected
    assert len(quality["affected_episodes"]) == 1
    native = read(ROOT / "telemetry-native-verification.json")
    assert native["metrics"]["co2_model_kg"] is None
    assert native["metrics"]["fuel_model_kg"] is None
    assert native["metrics"]["stops_per_vehicle"] is None
    assert len(assessment["runs"]) == 600 and len(assessment["paired"]) == 15
    assert all(row["pairs"] == 20 for row in assessment["paired"])
    ux = read(ROOT / "ux-performance.json")
    # Historical performance applies to the measured release, not future UI code.
    # Preserve and verify every original byte instead of freezing product development.
    snapshot = ROOT / "ux-measured-source.zip"
    if snapshot.exists():
        with zipfile.ZipFile(snapshot) as archived:
            assert set(archived.namelist()) == set(ux["measured_source_sha256"])
            for path, expected in ux["measured_source_sha256"].items():
                assert sha(archived.read(path)) == expected, path
    else:
        for path, expected in ux["measured_source_sha256"].items():
            assert sha((Path("frontend") / path).read_bytes()) == expected, path
    assert all(
        not row["violations"] and not row.get("page_errors") and row["horizontal_overflow_px"] <= 2
        for row in ux["accessibility"]["scans"]
    )
    print(
        f"Verified {count:,} source bins, {episodes:,} controller episodes, 140 learned-policy episodes and frozen ML/CV/UX provenance"
    )


if __name__ == "__main__":
    main()
