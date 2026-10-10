"""Publish complete actual cohorts and lossless evidence bundles, including failures."""

import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from atlas.city_data_v4 import stamp


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def interval(values, seed=51003):
    values = np.asarray(values)
    draws = np.random.default_rng(seed).integers(0, len(values), (20000, len(values)))
    return np.quantile(values[draws].mean(axis=1), [0.025, 0.975]).tolist()


def main():
    source = Path("data/control-v5")
    output = Path("artifacts/cities/v5")
    protocol = read("docs/control-v5-protocol.json")
    frozen = read(source / "frozen.json")
    selected = frozen["selected"]["candidate"]
    stages, bundles = {}, []
    for stage in ("development", "validation", "final"):
        runs = [
            r for city in protocol["cities"] for r in read(source / f"{stage}-{city}.json")["runs"]
        ]
        failures = [
            dict(city=city, **r)
            for city in protocol["cities"]
            for r in read(source / f"{stage}-{city}.json")["failures"]
        ]
        groups = defaultdict(list)
        for row in runs:
            groups[(row["city"], row["case"])].append(row)
        for (city, case), rows in groups.items():
            originals = []
            members = []
            for row in rows:
                encoded = (source / row["raw_archive"]).read_bytes()
                raw = gzip.decompress(encoded)
                assert sha(encoded) == row["archive_sha256"] and sha(raw) == row["raw_sha256"]
                original = json.loads(raw)
                assert original["metrics"] == row["metrics"]
                members.append(
                    {
                        "city": city,
                        "case": case,
                        "seed": row["seed"],
                        "candidate": row["candidate"],
                        "source_gzip_sha256": sha(encoded),
                        "raw_sha256": sha(raw),
                    }
                )
                originals.append(raw)
            payload = b"\n".join(originals) + b"\n"
            archive = output / f"control-{stage}-{city}-{case}.jsonl.gz"
            compressed = gzip.compress(payload, mtime=0)
            archive.write_bytes(compressed)
            bundles.append(
                {
                    "file": archive.name,
                    "stage": stage,
                    "city": city,
                    "case": case,
                    "gzip_sha256": sha(compressed),
                    "raw_sha256": sha(payload),
                    "raw_bytes": len(payload),
                    "members": members,
                }
            )
        stages[stage] = {"runs": runs, "failures": failures}
        write(
            output / f"control-{stage}.json",
            {
                "schema_version": "atlas-control-cohort-5.0",
                "stage": stage,
                "protocol_sha256": sha(Path("docs/control-v5-protocol.json").read_bytes()),
                **stages[stage],
            },
        )
    final = stages["final"]["runs"]
    expected = (
        len(protocol["cities"])
        * len(protocol["final_cases"])
        * len(protocol["final_seeds"])
        * (len(protocol["baselines"]) + 1)
    )
    assert len(final) == expected and not stages["final"]["failures"]
    assert len({(r["city"], r["case"], r["seed"], r["candidate"]) for r in final}) == expected
    cells, paired, regressions, aggregate = [], [], [], defaultdict(list)
    replay = {}
    for city in protocol["cities"]:
        for case in protocol["final_cases"]:
            rows = [r for r in final if r["city"] == city and r["case"] == case]
            indexed = {(r["candidate"], r["seed"]): r for r in rows}
            for seed in protocol["final_seeds"]:
                group = [indexed[(c, seed)] for c in [*protocol["baselines"], selected]]
                for field in (
                    "network_sha256",
                    "routes_sha256",
                    "initial_states",
                    "duration",
                    "scenario",
                ):
                    assert all(r[field] == group[0][field] for r in group)
                original, cached = (
                    indexed[("original_mpc", seed)],
                    indexed[("cached_original", seed)],
                )
                for field in ("mean_delay_s", "completed_trips", "mean_queue", "phase_switches"):
                    assert original["metrics"][field] == cached["metrics"][field], (
                        city,
                        case,
                        seed,
                        field,
                    )
            for candidate in [*protocol["baselines"], selected]:
                members = [r for r in rows if r["candidate"] == candidate]
                outcomes = {}
                coverage = {}
                for field in members[0]["metrics"]:
                    numbers = [
                        r["metrics"][field]
                        for r in members
                        if isinstance(r["metrics"].get(field), (int, float))
                    ]
                    outcomes[field] = float(np.mean(numbers)) if numbers else None
                    coverage[field] = len(numbers)
                cells.append(
                    {
                        "city": city,
                        "case": case,
                        "candidate": candidate,
                        "paired_seeds": len(members),
                        "mean_metrics": outcomes,
                        "telemetry_coverage": coverage,
                    }
                )
            for baseline in protocol["baselines"]:
                values = []
                for seed in protocol["final_seeds"]:
                    row, base = indexed[(selected, seed)], indexed[(baseline, seed)]
                    b = base["metrics"]["mean_delay_s"]
                    reduction = 100 * (b - row["metrics"]["mean_delay_s"]) / b
                    values.append(reduction)
                    aggregate[(baseline, city, seed)].append(reduction)
                    if reduction < 0:
                        regressions.append(
                            {
                                "city": city,
                                "case": case,
                                "seed": seed,
                                "baseline": baseline,
                                "delay_reduction_pct": reduction,
                            }
                        )
                paired.append(
                    {
                        "city": city,
                        "case": case,
                        "baseline": baseline,
                        "candidate": selected,
                        "pairs": len(values),
                        "mean_paired_delay_reduction_pct": float(np.mean(values)),
                        "ci95_pct": interval(values),
                        "paired_win_rate": float(np.mean(np.asarray(values) > 0)),
                        "worst_episode_reduction_pct": min(values),
                    }
                )
            for candidate in [*protocol["baselines"], selected]:
                first = indexed[(candidate, protocol["final_seeds"][0])]
                original = json.loads(gzip.decompress((source / first["raw_archive"]).read_bytes()))
                # Actual recorded replay. Omit per-lane inputs only for bandwidth.
                original["trace"] = [
                    {k: v for k, v in frame.items() if k not in {"lane_observations", "movements"}}
                    for frame in original["trace"]
                ]
                replay.setdefault(city, {}).setdefault(case, []).append(original)
    overall = []
    for baseline in protocol["baselines"]:
        blocks = [np.mean(values) for (b, _, _), values in aggregate.items() if b == baseline]
        overall.append(
            {
                "baseline": baseline,
                "mean_paired_delay_reduction_pct": float(np.mean(blocks)),
                "ci95_pct": interval(blocks),
                "independent_bootstrap_blocks": len(blocks),
                "method": "city/seed cluster bootstrap; all six scenario outcomes retained together",
            }
        )
    pressure = [r for r in paired if r["baseline"] == "max_pressure"]
    target = next(r for r in overall if r["baseline"] == "max_pressure")
    limits = protocol["promotion"]
    checks = {
        "mean_delay": target["mean_paired_delay_reduction_pct"]
        >= limits["minimum_mean_delay_reduction_vs_max_pressure_pct"],
        "worst_city_case": min(r["mean_paired_delay_reduction_pct"] for r in pressure)
        >= -limits["maximum_city_case_mean_regression_vs_max_pressure_pct"],
        "worst_episode": min(r["worst_episode_reduction_pct"] for r in pressure)
        >= -limits["maximum_single_episode_regression_vs_max_pressure_pct"],
        "modeled_signal_safety": all(r["metrics"]["modeled_safety_violations"] == 0 for r in final),
    }
    result = {
        "schema_version": "atlas-control-assessment-5.0",
        "generated_at": stamp(),
        "selected_candidate": selected,
        "final_episodes": len(final),
        "development_episodes": len(stages["development"]["runs"]),
        "validation_episodes": len(stages["validation"]["runs"]),
        "cached_original_identical_outcomes_pairs": len(protocol["cities"])
        * len(protocol["final_cases"])
        * len(protocol["final_seeds"]),
        "promotion_checks": checks,
        "promotion_criteria_pass": all(checks.values()),
        "production_promoted": False,
        "overall": overall,
        "city_case_results": cells,
        "paired_comparisons": paired,
        "regressions": sorted(regressions, key=lambda r: r["delay_reduction_pct"]),
        "limitations": [
            protocol["scope"],
            "Ten paired final seeds per city/scenario; intervals reflect simulator stochasticity, not uncertain municipal demand, geometry or driver parameters.",
            "Missing emission/stop telemetry is excluded and its coverage reported; no corrected values invented.",
            "Existing learned baseline is evaluated on new seeds and scenarios; its old training artifacts remain unchanged.",
            "No pedestrian/transit field outcomes or realized city congestion savings are supported.",
        ],
    }
    write(output / "control-assessment.json", result)
    write(
        output / "control-evidence-index.json",
        {"schema_version": "atlas-control-lossless-index-5.0", "bundles": bundles},
    )
    payload = json.dumps(
        {
            "schema_version": "atlas-control-replay-5.0",
            "seed": protocol["final_seeds"][0],
            "cities": replay,
        },
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    (output / "control-replay.json.gz").write_bytes(gzip.compress(payload, mtime=0))
    print(
        "Published",
        len(final),
        "final episodes; promotion checks",
        checks,
        "overall",
        overall,
        flush=True,
    )


if __name__ == "__main__":
    main()
