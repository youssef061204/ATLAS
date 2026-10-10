"""Small city/scenario payloads for actual replay and complete paired pilot evidence."""

import gzip
import json
from pathlib import Path

import numpy as np


def interval(values):
    values = np.asarray(values)
    draws = np.random.default_rng(51003).integers(0, len(values), (20000, len(values)))
    return np.quantile(values[draws].mean(axis=1), [0.025, 0.975]).tolist()


def main():
    root = Path("artifacts/cities/v5")
    assessment = json.loads((root / "control-assessment.json").read_text())
    replay = json.loads(gzip.decompress((root / "control-replay.json.gz").read_bytes()))
    final = json.loads((root / "control-final.json").read_text())["runs"]
    selected = assessment["selected_candidate"]

    def policy(candidate):
        return "portfolio_v5" if candidate == selected else candidate

    def public(row, include_trace=False):
        result = {
            key: row[key]
            for key in (
                "city",
                "seed",
                "duration",
                "scenario",
                "network_sha256",
                "routes_sha256",
                "metrics",
            )
        }
        result.update(
            policy=policy(row["candidate"]),
            source_policy=row["policy"],
            trace=row.get("trace", []) if include_trace else [],
            decisions=row.get("decisions", []) if include_trace else [],
        )
        return result

    pilots = {}
    for city, cases in replay["cities"].items():
        for case, first_runs in cases.items():
            summaries, paired = [], []
            rows = [r for r in final if r["city"] == city and r["case"] == case]
            for cell in assessment["city_case_results"]:
                if cell["city"] != city or cell["case"] != case:
                    continue
                candidate = cell["candidate"]
                lookup = {r["seed"]: r for r in rows if r["candidate"] == candidate}
                comparisons = []
                for baseline in {r["candidate"] for r in rows}:
                    base = {r["seed"]: r for r in rows if r["candidate"] == baseline}
                    differences, percentages = [], []
                    for seed in sorted(lookup):
                        a, b = (
                            lookup[seed]["metrics"]["mean_delay_s"],
                            base[seed]["metrics"]["mean_delay_s"],
                        )
                        differences.append(b - a)
                        percentages.append(100 * (b - a) / b)
                    comparisons.append(
                        {
                            "baseline": policy(baseline),
                            "n": len(percentages),
                            "mean_paired_reduction_pct": float(np.mean(percentages)),
                            "ci95": interval(percentages),
                        }
                    )
                    if candidate == selected:
                        paired.append(
                            {
                                "city": city,
                                "baseline": policy(baseline),
                                "pairs": len(percentages),
                                "paired_difference_ci95": interval(differences),
                                "paired_percent_ci95": interval(percentages),
                            }
                        )
                summaries.append(
                    {
                        "city": city,
                        "policy": policy(candidate),
                        "seeds": cell["paired_seeds"],
                        "mean_delay_s": cell["mean_metrics"]["mean_delay_s"],
                        "sd": None,
                        "ci95": None,
                        "decision_ms_p95": cell["mean_metrics"]["decision_ms_p95"],
                        "comparisons": comparisons,
                    }
                )
            payload = {
                "scope": "ATLAS 5 independently paired exploratory SUMO; assumed demand and signal plans; experimental portfolio not promoted",
                "case": case,
                "seed_count": 10,
                "production_promoted": False,
                "promotion_checks": assessment["promotion_checks"],
                "runs": [public(row, True) for row in first_runs],
                "summaries": summaries,
                "paired": paired,
                "failures": [],
            }
            (root / f"studio-{city}-{case}.json").write_text(
                json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8"
            )
            pilot = pilots.setdefault(case, {**payload, "runs": [], "summaries": [], "paired": []})
            pilot["runs"].extend(public(row) for row in rows)
            pilot["summaries"].extend(summaries)
            pilot["paired"].extend(paired)
    for case, payload in pilots.items():
        (root / f"pilot-{case}.json").write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        )
    print("Prepared 30 city/scenario replays and six complete 10-seed pilot payloads")


if __name__ == "__main__":
    main()
