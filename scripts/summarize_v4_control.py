"""Derive complete paired controller reports, including unsuccessful transfer cities."""

import gzip
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path("artifacts/cities/v4")
CITIES = ("toronto", "london", "seattle", "austin", "calgary")


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def comparison(rows, baselines):
    reductions = []
    differences = []
    for row in rows:
        other = next(item for item in baselines if item["seed"] == row["seed"])
        for key in (
            "city",
            "seed",
            "network_sha256",
            "routes_sha256",
            "initial_states",
            "duration",
            "scenario",
        ):
            if row[key] != other[key]:
                raise ValueError(f"Unpaired learned control input: {key}")
        a, b = other["metrics"]["mean_delay_s"], row["metrics"]["mean_delay_s"]
        differences.append(a - b)
        reductions.append(100 * (a - b) / a)
    values = np.array(reductions)
    bootstrap = np.random.default_rng(44).integers(0, len(values), (20000, len(values)))
    return {
        "pairs": len(values),
        "mean_paired_reduction_pct": float(values.mean()),
        "reduction_ci95": list(
            map(float, np.percentile(values[bootstrap].mean(axis=1), [2.5, 97.5]))
        ),
        "mean_delay_difference_s": float(np.mean(differences)),
        "improved_seeds": int((values > 0).sum()),
    }


def main():
    cohorts = {
        regime: read(f"controller-heldout-{regime}.json") for regime in ("nominal", "low", "high")
    }
    for regime, study in cohorts.items():
        if len(study["runs"]) != 600 or study["failures"]:
            raise ValueError(f"Incomplete {regime} cohort")
    q = read("cooperative-q-results.json")
    archive = read("cooperative-q-archives.json")
    raw_q = []
    with zipfile.ZipFile(ROOT / archive["archive"]) as bundle:
        for row in q["runs"]:
            raw = json.loads(gzip.decompress(bundle.read(row["archive"])))
            assert raw["metrics"] == row["metrics"]
            raw_q.append(raw)
    learned = []
    for city in CITIES:
        rows = [r for r in raw_q if r["city"] == city]
        learned.append(
            {
                "city": city,
                "target_city_training_episodes": 0,
                "seeds": len(rows),
                "mean_delay_s": float(np.mean([r["metrics"]["mean_delay_s"] for r in rows])),
                "modeled_safety_violations": sum(
                    r["metrics"]["modeled_safety_violations"] for r in rows
                ),
                "comparisons": {
                    policy: comparison(
                        rows,
                        [
                            r
                            for r in cohorts["nominal"]["runs"]
                            if r["city"] == city and r["candidate"] == policy
                        ],
                    )
                    for policy in ("fixed", "max_pressure", "original_mpc", "actuated")
                },
            }
        )
    result = {
        "schema_version": "atlas-controller-complete-report-4.0",
        "source_sha256": {
            f"controller-heldout-{regime}.json": hashlib.sha256(
                (ROOT / f"controller-heldout-{regime}.json").read_bytes()
            ).hexdigest()
            for regime in cohorts
        },
        "deterministic_heldout_episodes": sum(len(s["runs"]) for s in cohorts.values()),
        "demand_regimes": {
            regime: [row for row in study["summaries"] if row["candidate"] == "cached_original"]
            for regime, study in cohorts.items()
        },
        "cooperative_q_zero_shot": learned,
        "learned_policy_sha256": q["policy_sha256"],
        "promoted": False,
        "scope": "Exploratory OSM SUMO corridors; half/full/double generated OD. Bootstrap intervals measure simulator-seed variation, not field or model uncertainty.",
        "limitations": [
            "Cached MPC preserves original traffic behavior; computational optimization is separate from traffic improvement.",
            "Cooperative Q is trained on four cities and evaluated on the fifth with no target-city fitting. It regresses in some cities; no universal superiority or operational promotion.",
            "Learned policy was tested in nominal demand only. Low/high robustness belongs to the deterministic cohort.",
            "No surveyed municipal timing, bus/pedestrian delay, calibrated field queues or realized emissions benefits.",
        ],
    }
    (ROOT / "controller-results.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    print("Derived 1,800 deterministic held-out episodes and all 100 frozen zero-shot outcomes")


if __name__ == "__main__":
    main()
