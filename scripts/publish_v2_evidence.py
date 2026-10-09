"""Derive statistics and compact presentation from actual complete experiments."""

import gzip
import json
from pathlib import Path

import numpy as np
from atlas.city_network import sha
from scipy import stats

ROOT = Path("artifacts/cities")


def summary(runs):
    rows = []
    for city in sorted({r["city"] for r in runs}):
        for policy in ("fixed", "max_pressure", "original_mpc", "risk_mpc"):
            selected = [r for r in runs if r["city"] == city and r["policy"] == policy]
            if not selected:
                continue
            values = np.array([r["metrics"]["mean_delay_s"] for r in selected])
            sd = float(values.std(ddof=1))
            ci = (
                list(
                    map(
                        float,
                        stats.t.interval(
                            0.95, len(values) - 1, loc=values.mean(), scale=stats.sem(values)
                        ),
                    )
                )
                if sd
                else [float(values.mean())] * 2
            )
            numeric = [k for k, v in selected[0]["metrics"].items() if isinstance(v, (float, int))]
            means = {k: float(np.mean([r["metrics"][k] for r in selected])) for k in numeric}
            rows.append(
                {
                    "city": city,
                    "policy": policy,
                    "seeds": len(values),
                    "mean_delay_s": float(values.mean()),
                    "sd": sd,
                    "ci95": ci,
                    "decision_ms_p95": means["decision_ms_p95"],
                    "mean_metrics": means,
                }
            )
    return rows


def paired(runs):
    rows = []
    rng = np.random.default_rng(81723)
    for city in sorted({r["city"] for r in runs}):
        candidate = {r["seed"]: r for r in runs if r["city"] == city and r["policy"] == "risk_mpc"}
        for baseline in ("fixed", "max_pressure", "original_mpc"):
            reference = {
                r["seed"]: r for r in runs if r["city"] == city and r["policy"] == baseline
            }
            if set(reference) != set(candidate) or len(candidate) < 2:
                raise ValueError("Incomplete paired cohort")
            difference, percent = [], []
            for seed in sorted(candidate):
                a, b = reference[seed], candidate[seed]
                for key in (
                    "network_sha256",
                    "routes_sha256",
                    "initial_states",
                    "duration",
                    "scenario",
                    "platform",
                ):
                    if a[key] != b[key]:
                        raise ValueError("Mismatched paired input")
                x, y = a["metrics"]["mean_delay_s"], b["metrics"]["mean_delay_s"]
                difference.append(x - y)
                percent.append(100 * (x - y) / x)
            idx = rng.integers(0, len(difference), size=(20000, len(difference)))
            delta = np.array(difference)
            pct = np.array(percent)
            rows.append(
                {
                    "city": city,
                    "baseline": baseline,
                    "pairs": len(delta),
                    "mean_delay_reduction_s": float(delta.mean()),
                    "paired_difference_ci95": list(
                        map(float, np.quantile(delta[idx].mean(axis=1), [0.025, 0.975]))
                    ),
                    "mean_paired_reduction_pct": float(pct.mean()),
                    "paired_percent_ci95": list(
                        map(float, np.quantile(pct[idx].mean(axis=1), [0.025, 0.975]))
                    ),
                    "wins": int(np.sum(delta > 0)),
                    "ties": int(np.sum(np.isclose(delta, 0))),
                    "definition": "positive = lower prototype delay",
                }
            )
    return rows


def main():
    protocol = json.loads(Path("docs/atlas-2-protocol.json").read_text(encoding="utf-8"))
    suites = []
    for filename, expected in (("five-city-nominal.json", 400), ("transfer.json", 160)):
        path = ROOT / filename
        data = json.loads(
            path.read_text(encoding="utf-8")
            if path.exists()
            else gzip.decompress(Path(str(path) + ".gz").read_bytes()).decode("utf-8")
        )
        runs = data["runs"]
        if len(runs) != expected:
            raise ValueError(f"{filename}: expected {expected} actual runs")
        for run in runs:
            if (
                run["controller_sha256"]
                != protocol["frozen_source_sha256"]["backend/atlas/control_v2.py"]
                or run["harness_sha256"]
                != protocol["frozen_source_sha256"]["backend/atlas/evaluation/network_v2.py"]
            ):
                raise ValueError("Frozen source mismatch")
            if run["metrics"]["modeled_safety_violations"]:
                raise ValueError("Modeled safety violation")
        suites.append(
            {
                "suite": filename,
                "scope": data["scope"],
                "runs": len(runs),
                "summaries": summary(runs),
                "paired": paired(runs),
            }
        )
        if path.exists():
            path.with_suffix(".json.gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
        if filename == "five-city-nominal.json":
            selected_seed = min(r["seed"] for r in runs)
            compact = []
            for run in runs:
                reduced = {k: v for k, v in run.items() if k not in {"trace", "decisions"}}
                reduced["trace"] = run["trace"] if run["seed"] == selected_seed else []
                reduced["decisions"] = run["decisions"] if run["seed"] == selected_seed else []
                compact.append(reduced)
            payload = {
                "schema_version": "atlas-city-experiments-2.0",
                "scope": data["scope"],
                "runs": compact,
                "summaries": suites[-1]["summaries"],
                "paired": suites[-1]["paired"],
                "failures": data["failures"],
                "presentation_note": "All 20 seeds' metrics retained; web replay uses the predeclared first seed, 20001. Complete traces in lossless five-city-nominal.json.gz.",
            }
            (ROOT / "experiments.json").write_text(
                json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8"
            )
    (ROOT / "study-summary.json").write_text(
        json.dumps(
            {"protocol_sha256": sha("docs/atlas-2-protocol.json"), "suites": suites},
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    lines = [
        "# ATLAS 2.0 measured evidence\n",
        "This increment is experimental. The prototype is not promoted over the production controller. No field or proprietary-controller superiority is claimed.\n",
    ]
    for suite in suites:
        lines += [
            f"## {suite['suite']}\n",
            suite["scope"] + "\n",
            "| City | Controller | Mean delay ± sample SD | Mean 95% CI | Seeds |\n|---|---|---:|---|---:|",
        ]
        for r in suite["summaries"]:
            lines.append(
                f"| {r['city']} | {r['policy']} | {r['mean_delay_s']:.3f} ± {r['sd']:.3f} s | {r['ci95'][0]:.3f}–{r['ci95'][1]:.3f} | {r['seeds']} |"
            )
        lines += [
            "\nPaired prototype comparisons (positive means lower delay):\n",
            "| City | Baseline | Mean paired reduction | Bootstrap 95% CI | Wins |\n|---|---|---:|---|---:|",
        ]
        for r in suite["paired"]:
            lines.append(
                f"| {r['city']} | {r['baseline']} | {r['mean_paired_reduction_pct']:.2f}% | {r['paired_percent_ci95'][0]:.2f}–{r['paired_percent_ci95'][1]:.2f}% | {r['wins']}/{r['pairs']} |"
            )
    lines += [
        "\n## Interpretation and limits\n",
        "Five-city routes are assumed demand on small OSM corridors. The prototype can lose to frozen MPC or fixed timing. The topology fallback is pressure control, not proof of improved cooperative optimization. Ingolstadt improvements must be compared with pressure separately. Search latency can be worse. The protocol was frozen before the final cohorts; all seeds and failures remain in the raw evidence.\n",
        "Controller/demand/source hashes and all metrics are in `artifacts/cities/study-summary.json`. Full raw traces are losslessly compressed alongside it. This study does not establish real-city calibration, pedestrian/transit/emergency outcomes, multi-regime reliability or commercial readiness.\n",
    ]
    Path("docs/atlas-2-results.md").write_text("\n".join(lines), encoding="utf-8")
    for suite in suites:
        for r in suite["paired"]:
            print(
                r["city"],
                r["baseline"],
                round(r["mean_paired_reduction_pct"], 2),
                "%",
                r["wins"],
                "wins",
                flush=True,
            )


if __name__ == "__main__":
    main()
