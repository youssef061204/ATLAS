"""Predeclared successive-halving/validation/frozen-test signal-control study."""

import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace

import numpy as np
from scipy import stats

from atlas import config
from atlas.control import ControlConfig
from atlas.evaluation.artifacts import checksum, write_artifact
from atlas.evaluation.data import RESCO_REVISION
from atlas.evaluation.signal_lab import assert_paired, run

WORK = config.DATA / "signal-study"
WORK.mkdir(parents=True, exist_ok=True)
VARIANTS = ["nominal", "low", "peak", "imbalance", "burst"]
TRAIN = [(1001 + i, VARIANTS[i // 2]) for i in range(10)]
VALIDATION = [(3001 + i, variant) for i, variant in enumerate(VARIANTS)]
TEST = list(range(5001, 5011))
ABLATION_SEEDS = list(range(6001, 6006))
TRANSFER_SEEDS = list(range(7001, 7006))
STRESS = [(8001 + i, variant) for i, variant in enumerate(VARIANTS)]


def candidates():
    base = ControlConfig()
    pressure = [
        base,
        replace(base, switch_penalty=0.25),
        replace(base, min_green=10, switch_penalty=0.25, decision_interval=2),
        replace(base, min_green=15, switch_penalty=0.5, decision_interval=3),
        replace(base, switch_penalty=0.25, wait_weight=0.25, starvation_weight=0.5),
        replace(base, switch_penalty=0.5, wait_weight=1, starvation_weight=0.5, queue_weight=0.25),
        replace(
            base,
            min_green=10,
            switch_penalty=0.25,
            wait_weight=0.5,
            starvation_weight=1,
            forecast_weight=0.25,
        ),
        replace(
            base, switch_penalty=0.5, wait_weight=0.25, starvation_weight=0.5, forecast_weight=0.5
        ),
        replace(base, switch_penalty=0.25, wait_weight=0.25, downstream_weight=0.5),
        replace(base, switch_penalty=0.25, wait_weight=0.25, downstream_weight=2),
        replace(base, switch_penalty=0.25, max_green=45, forecast_weight=0.25, forecast_seconds=30),
        replace(base, switch_penalty=0.25, decision_interval=5),
    ]
    mpc = [
        replace(
            base,
            family="mpc",
            horizon=h,
            beam_width=b,
            service_rate=s,
            forecast_weight=f,
            queue_weight=0.15,
            starvation_weight=0.25,
            switch_penalty=0.5,
        )
        for h, b, s, f in [
            (20, 2, 0.5, 0),
            (20, 4, 0.5, 1),
            (30, 4, 0.5, 0),
            (30, 4, 0.5, 1),
            (40, 4, 0.5, 1),
            (30, 6, 0.35, 1),
            (30, 6, 0.65, 1),
            (30, 4, 0.5, 0.5),
        ]
    ]
    return {f"pressure_{i:02d}": c for i, c in enumerate(pressure)} | {
        f"mpc_{i:02d}": c for i, c in enumerate(mpc)
    }


def protocol():
    sets = [
        set(s for s, v in TRAIN),
        set(s for s, v in VALIDATION),
        set(TEST),
        set(ABLATION_SEEDS),
        set(TRANSFER_SEEDS),
        set(s for s, v in STRESS),
    ]
    if any(a & b for i, a in enumerate(sets) for b in sets[i + 1 :]):
        raise ValueError("Experiment split leakage")
    return {
        "version": "signal-study-v2",
        "execution": "Linux SUMO 1.27.1; audited fresh replay. Windows same-seed drift is documented and not used for final evaluation.",
        "routing": "Resolve published OD trips using seeded duarouter before the episode; assert identical resolved path SHA-256 for every paired controller.",
        "ablation_variants": [
            "full",
            "no_forecast",
            "forecast_on",
            "no_downstream",
            "no_starvation",
            "no_switch_penalty",
            "pressure_only",
            "queue_only",
        ],
        "source_revision": RESCO_REVISION,
        "tuning": TRAIN,
        "validation": VALIDATION,
        "test": TEST,
        "ablations": ABLATION_SEEDS,
        "transfer": TRANSFER_SEEDS,
        "stress": STRESS,
        "historical_audit_seeds": [42, 43, 44],
        "tuning_begin": 25200,
        "test_begin": 27000,
        "duration_seconds": 1800,
        "warmup_seconds": 0,
        "common_constraints": {"min_green": 10, "max_green": 60, "yellow": 3, "all_red": 2},
        "search": "20 declared candidates on 2 nominal tuning seeds; best 3 per family on all 10 tuning cases; 6 finalists on 5 separate validation cases",
        "selection": "minimum mean all-scheduled vehicle delay across five equally weighted validation demand variants; no final-test selection",
        "candidates": {name: asdict(c) for name, c in candidates().items()},
        "transfer_scenario": "RESCO Ingolstadt1, 16:00–16:30, without retuning; source fixed cycle clamped to common 10–60 s bounds",
        "forecast": "causal lane-entry EWMA at 1 Hz; no future trips; METR-LA highway speeds are a different target and are not misused as 10-second junction arrivals",
        "cache": "network/demand/controller/harness SHA-256 and full settings must match",
    }


def persist_protocol():
    # Protocol is a study specification rather than a BenchmarkArtifact.
    p = config.ROOT / "docs" / "signal-control-protocol.json"
    payload = json.loads(json.dumps(protocol()))
    if p.exists() and json.loads(p.read_text(encoding="utf-8")) != payload:
        raise ValueError("The declared protocol changed; create a new study instead")
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return checksum(p)


def _execute(spec):
    return run(**spec)


def batch(specs):
    with ProcessPoolExecutor(max_workers=2) as pool:
        return list(pool.map(_execute, specs))


def brief(result):
    return {key: value for key, value in result.items() if key != "trace"}


def audit():
    persist_protocol()
    specs = [
        {"policy": p, "seed": s, "begin": 27000}
        for s in [42, 43, 44]
        for p in ["fixed", "max_pressure", "atlas_original"]
    ]
    specs.append({"policy": "atlas_fixed_equivalent", "seed": 42, "begin": 27000})
    results = batch(specs)
    for i in range(3):
        assert_paired(results[i * 3 : i * 3 + 3])
    assert results[0]["metrics"]["mean_delay_s"] == results[-1]["metrics"]["mean_delay_s"]
    # Repeat one run without cache to verify episode reset and deterministic state.
    repeat = run("atlas_original", 42, begin=27000, reuse=False)
    deterministic = repeat["metrics"]["mean_delay_s"] == results[2]["metrics"]["mean_delay_s"]
    if not deterministic:
        raise ValueError("Fresh same-seed SUMO replay is not deterministic")
    path = WORK / "audit.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for r in results[:3]:
        print("AUDIT", r["signature"]["policy"], r["metrics"], flush=True)
    plots(results[:3], "original-diagnostics")
    return write_artifact(
        "signal_controller_audit",
        benchmark_type="signal_control_audit",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1",
        dataset_version=RESCO_REVISION,
        model="Unchanged fixed, max-pressure, and original cyclic ATLAS",
        seed=[42, 43, 44],
        split={
            "purpose": "Previously observed historical audit only; never used for new-controller selection"
        },
        metrics={
            "fairness_checks_passed": True,
            "fresh_seed_reset_deterministic": deterministic,
            "fixed_equivalent_delay_s": results[-1]["metrics"]["mean_delay_s"],
            "seed42": {r["signature"]["policy"]: r["metrics"] for r in results[:3]},
        },
        scope="Historical diagnosis and harness validation, not new held-out accuracy.",
        methodology={
            "observations": "Fresh 1-Hz lane/vehicle subscriptions; no forecasting in original ATLAS; every actuator state is a legal source phase or protected clearance.",
            "baseline": "Existing choose_phase logic remains unchanged. Deterministic sorted movement summation removes Python hash-order variation in density arithmetic.",
        },
        results={
            "runs": [brief(r) for r in results],
            "diagnostic_plots_prefix": "plots/control/original-diagnostics",
        },
    )


def train():
    persist_protocol()
    configs = candidates()
    initial = [(1001, "nominal"), (1002, "nominal")]
    # These are the declared first two TRAIN cases (same nominal demand).
    results = batch(
        [
            {"policy": name, "seed": seed, "variant": variant, "settings": c}
            for name, c in configs.items()
            for seed, variant in initial
        ]
    )
    ranking = {
        name: float(
            np.mean(
                [r["metrics"]["mean_delay_s"] for r in results if r["signature"]["policy"] == name]
            )
        )
        for name in configs
    }
    finalists = []
    for family in ["pressure", "mpc"]:
        finalists.extend(
            sorted([name for name, c in configs.items() if c.family == family], key=ranking.get)[:3]
        )
    extra = batch(
        [
            {"policy": name, "seed": seed, "variant": variant, "settings": configs[name]}
            for name in finalists
            for seed, variant in TRAIN[2:]
        ]
    )
    complete = results + extra
    output = {
        "initial_scores": ranking,
        "promoted": finalists,
        "runs": [brief(r) for r in complete],
        "tuning_scores": {
            name: float(
                np.mean(
                    [
                        r["metrics"]["mean_delay_s"]
                        for r in complete
                        if r["signature"]["policy"] == name
                    ]
                )
            )
            for name in finalists
        },
    }
    (WORK / "training.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print("TUNING PROMOTED", output["tuning_scores"], flush=True)
    return output


def validate():
    protocol_sha = persist_protocol()
    training = json.loads((WORK / "training.json").read_text(encoding="utf-8"))
    configs = candidates()
    names = training["promoted"]
    specs = [
        {"policy": name, "seed": seed, "variant": variant, "settings": configs[name]}
        for name in names
        for seed, variant in VALIDATION
    ]
    specs += [
        {"policy": name, "seed": seed, "variant": variant}
        for name in ["fixed", "max_pressure", "atlas_original"]
        for seed, variant in VALIDATION
    ]
    results = batch(specs)
    for seed, _variant in VALIDATION:
        assert_paired([r for r in results if r["signature"]["seed"] == seed])
    scores = {
        name: float(
            np.mean(
                [r["metrics"]["mean_delay_s"] for r in results if r["signature"]["policy"] == name]
            )
        )
        for name in names
    }
    winner = min(scores, key=scores.get)
    frozen = {
        "selected": winner,
        "settings": asdict(configs[winner]),
        "validation_scores": scores,
        "protocol_sha256": protocol_sha,
        "controller_sha256": checksum(config.ROOT / "backend/atlas/control.py"),
        "harness_sha256": checksum(config.ROOT / "backend/atlas/evaluation/signal_lab.py"),
        "frozen_before_test": True,
    }
    (WORK / "frozen.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    # Published, immutable selection evidence precedes final-test execution.
    (config.ROOT / "docs" / "signal-controller-frozen.json").write_text(
        json.dumps(frozen, indent=2), encoding="utf-8"
    )
    (WORK / "validation.json").write_text(
        json.dumps([brief(r) for r in results], indent=2), encoding="utf-8"
    )
    print("FROZEN VALIDATION WINNER", frozen, flush=True)
    return frozen


def frozen_config():
    value = json.loads((WORK / "frozen.json").read_text(encoding="utf-8"))
    if (
        value["protocol_sha256"] != persist_protocol()
        or value["controller_sha256"] != checksum(config.ROOT / "backend/atlas/control.py")
        or value["harness_sha256"]
        != checksum(config.ROOT / "backend/atlas/evaluation/signal_lab.py")
    ):
        raise ValueError("Policy/harness/protocol changed after selection")
    return ControlConfig(**value["settings"]), value


METRICS = [
    "mean_delay_s",
    "median_delay_s",
    "mean_queue",
    "max_queue",
    "throughput_vehicles_per_hour",
    "completed_trips",
    "stops_per_vehicle",
    "completed_mean_travel_time_s",
    "phase_switches",
    "lost_transition_seconds",
    "decision_ms_p95",
]


def aggregate(results):
    output = {}
    for name in sorted({r["signature"]["policy"] for r in results}):
        rows = [r for r in results if r["signature"]["policy"] == name]
        output[name] = {}
        for key in METRICS:
            x = np.array([r["metrics"][key] for r in rows], dtype=float)
            se = stats.sem(x) if len(x) > 1 else 0
            half = stats.t.ppf(0.975, len(x) - 1) * se if len(x) > 1 else 0
            output[name][key] = {
                "mean": float(x.mean()),
                "std": float(x.std(ddof=1)) if len(x) > 1 else 0,
                "ci95": [float(x.mean() - half), float(x.mean() + half)],
            }
    return output


def paired_stats(results, reference):
    a = {
        r["signature"]["seed"]: r["metrics"]["mean_delay_s"]
        for r in results
        if r["signature"]["policy"] == "atlas_improved"
    }
    b = {
        r["signature"]["seed"]: r["metrics"]["mean_delay_s"]
        for r in results
        if r["signature"]["policy"] == reference
    }
    if a.keys() != b.keys():
        raise ValueError("Unpaired statistics")
    difference = np.array([b[s] - a[s] for s in sorted(a)])
    percent = np.array([(b[s] - a[s]) / b[s] * 100 for s in sorted(a)])
    rng = np.random.default_rng(982451653)
    indices = rng.integers(0, len(difference), (20000, len(difference)))
    return {
        "paired_delay_reduction_s": float(difference.mean()),
        "paired_delay_reduction_ci95_s": np.quantile(
            difference[indices].mean(axis=1), [0.025, 0.975]
        ).tolist(),
        "mean_paired_improvement_pct": float(percent.mean()),
        "paired_improvement_ci95_pct": np.quantile(
            percent[indices].mean(axis=1), [0.025, 0.975]
        ).tolist(),
        "paired_t_test_p": float(stats.ttest_1samp(difference, 0).pvalue)
        if difference.std() > 0
        else None,
        "paired_cohen_dz": float(difference.mean() / difference.std(ddof=1))
        if difference.std() > 0
        else None,
        "wins": int(np.sum(difference > 0)),
        "seeds": len(a),
    }


def final():
    selected, frozen = frozen_config()
    results = batch(
        [
            {
                "policy": p,
                "seed": seed,
                "begin": 27000,
                "settings": selected if p == "atlas_improved" else None,
            }
            for seed in TEST
            for p in ["fixed", "max_pressure", "atlas_original", "atlas_improved"]
        ]
    )
    for seed in TEST:
        assert_paired([r for r in results if r["signature"]["seed"] == seed])
    metrics = {
        "controllers": aggregate(results),
        "runs_per_controller": len(TEST),
        "paired_comparisons": {
            p: paired_stats(results, p) for p in ["fixed", "max_pressure", "atlas_original"]
        },
    }
    (WORK / "final.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    plots([r for r in results if r["signature"]["seed"] == TEST[0]], "improved-diagnostics")
    artifact = write_artifact(
        "improved_signal_control",
        benchmark_type="signal_control",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1",
        dataset_version=RESCO_REVISION,
        model="ATLAS "
        + selected.family
        + " feedback controller; unchanged fixed/max-pressure/original comparators",
        seed=TEST,
        split={
            "tuning": TRAIN,
            "validation": VALIDATION,
            "test": TEST,
            "test_begin": 27000,
            "test_duration": 1800,
        },
        metrics=metrics,
        scope="Simulated interventions under published real-world-derived demand; ten new held-out seeds, not field validation.",
        methodology={
            "selection": frozen,
            "delay": "All scheduled vehicles: timeLoss+departDelay, including unfinished and noninserted trips.",
            "constraints": protocol()["common_constraints"],
            "warmup_seconds": 0,
            "teleport": -1,
            "statistics": "Paired seed bootstrap 20,000 resamples with fixed RNG; paired t-test exploratory; t CI on controller means.",
            "baseline": "Original 66.45 s historical artifact remains intact; original controller also reevaluated on these new paired seeds.",
            "forecast": protocol()["forecast"],
        },
        results={
            "runs": [brief(r) for r in results],
            "replay": {
                r["signature"]["policy"]: r["trace"]
                for r in results
                if r["signature"]["seed"] == TEST[0]
            },
            "replay_seed": TEST[0],
            "legal_states": results[0]["states"],
        },
    )
    print("FINAL", json.dumps(metrics), flush=True)
    return artifact


def ablate():
    selected, _ = frozen_config()
    configs = {
        "full": selected,
        "no_forecast": replace(selected, forecast_weight=0),
        "forecast_on": replace(selected, forecast_weight=0.5),
        "no_downstream": replace(selected, downstream_weight=0),
        "no_starvation": replace(selected, starvation_weight=0, starvation_limit=10**9),
        "no_switch_penalty": replace(selected, switch_penalty=0),
        "pressure_only": ControlConfig(
            min_green=selected.min_green,
            decision_interval=selected.decision_interval,
            switch_penalty=0,
            starvation_limit=10**9,
        ),
        "queue_only": ControlConfig(
            family="queue",
            min_green=selected.min_green,
            switch_penalty=0,
            downstream_weight=0,
            starvation_limit=10**9,
        ),
    }
    results = batch(
        [
            {"policy": name, "seed": seed, "begin": 27000, "settings": c}
            for name, c in configs.items()
            for seed in ABLATION_SEEDS
        ]
    )
    for seed in ABLATION_SEEDS:
        assert_paired([r for r in results if r["signature"]["seed"] == seed])
    metrics = aggregate(results)
    paired_results = [
        {
            **r,
            "signature": {
                **r["signature"],
                "policy": "atlas_improved"
                if r["signature"]["policy"] == "full"
                else r["signature"]["policy"],
            },
        }
        for r in results
    ]
    return write_artifact(
        "signal_control_ablations",
        benchmark_type="signal_control_ablation",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1",
        dataset_version=RESCO_REVISION,
        model="Frozen controller one-component removals; no ablation retuning",
        seed=ABLATION_SEEDS,
        split={
            "held_out_diagnostic_seeds": ABLATION_SEEDS,
            "selection": "None; final policy remains frozen",
        },
        metrics={
            "controllers": metrics,
            "runs_per_controller": len(ABLATION_SEEDS),
            "paired_full_vs_variant": {
                name: paired_stats(paired_results, name) for name in configs if name != "full"
            },
        },
        scope="Separate unseen seeds, post-selection mechanistic evidence; not a new selection set.",
        results={
            "settings": {n: asdict(c) for n, c in configs.items()},
            "runs": [brief(r) for r in results],
        },
    )


def generalize():
    selected, _ = frozen_config()
    specs = [
        {
            "policy": p,
            "seed": seed,
            "variant": variant,
            "begin": 27000,
            "settings": selected if p == "atlas_improved" else None,
        }
        for seed, variant in STRESS
        for p in ["fixed", "max_pressure", "atlas_original", "atlas_improved"]
    ]
    specs += [
        {
            "policy": p,
            "seed": seed,
            "scenario": "ingolstadt1",
            "begin": 57600,
            "settings": selected if p == "atlas_improved" else None,
        }
        for seed in TRANSFER_SEEDS
        for p in ["fixed", "max_pressure", "atlas_improved"]
    ]
    results = batch(specs)
    for seed in [s for s, v in STRESS] + TRANSFER_SEEDS:
        assert_paired([r for r in results if r["signature"]["seed"] == seed])
    transfer = [r for r in results if r["signature"]["scenario"] == "ingolstadt1"]
    return write_artifact(
        "signal_control_generalization",
        benchmark_type="signal_control_transfer",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1 perturbations / Ingolstadt1",
        dataset_version=RESCO_REVISION,
        model="Frozen ATLAS parameters without scenario-specific tuning",
        seed=[s for s, v in STRESS] + TRANSFER_SEEDS,
        split={
            "perturbation_seeds": STRESS,
            "transfer_seeds": TRANSFER_SEEDS,
            "transfer_begin": 57600,
        },
        metrics={
            "transfer_controllers": aggregate(transfer),
            "transfer_paired_comparisons": {
                p: paired_stats(transfer, p) for p in ["fixed", "max_pressure"]
            },
            "stress_by_variant": {
                v: aggregate(
                    [
                        r
                        for r in results
                        if r["signature"]["variant"] == v
                        and r["signature"]["scenario"] == "cologne1"
                    ]
                )
                for v in VARIANTS
            },
        },
        scope="Five unseen transfer seeds; one unseen seed per demand perturbation. Small stress sample, no general city-wide guarantee.",
        methodology={
            "transfer_fixed": "Published green durations 38/6/37 clamped to common 10–60 second safety bounds: 38/10/37. Shared 3 s yellow + 2 s all-red. No weakening of max-pressure."
        },
        results={"runs": [brief(r) for r in results]},
    )


def plots(results, prefix):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    folder = config.ARTIFACTS / "benchmarks" / "plots" / "control"
    folder.mkdir(parents=True, exist_ok=True)
    columns = {
        "queue": "Queue (vehicles)",
        "total_delay_s": "Cumulative observed delay (s)",
        "phase": "Phase index",
        "switches": "Phase switches",
        "cumulative_departures": "Cumulative completed trips",
        "total_pressure": "Sum of phase pressures",
        "cumulative_objective": "Cumulative queue + switching objective",
        "starved_lanes": "Lanes without departures for 180 s",
    }
    for key, title in columns.items():
        fig, axis = plt.subplots(figsize=(10, 4))
        for row in results:
            trace = row["trace"]
            x = [f["t"] for f in trace]
            y = [len(f[key]) if key == "starved_lanes" else f[key] for f in trace]
            axis.plot(x, y, label=row["signature"]["policy"], linewidth=1)
        axis.set(
            xlabel="Simulation seconds",
            ylabel=title,
            title=prefix.replace("-", " ") + " / " + title,
        )
        axis.legend(fontsize=8)
        axis.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(folder / f"{prefix}-{key}.png", dpi=140)
        plt.close(fig)


def publish_search():
    frozen_config()
    training = json.loads((WORK / "training.json").read_text(encoding="utf-8"))
    validation = json.loads((WORK / "validation.json").read_text(encoding="utf-8"))
    return write_artifact(
        "signal_control_selection",
        benchmark_type="signal_control_selection",
        data_provenance="real-world-derived",
        dataset="RESCO Cologne1 tuning variants",
        dataset_version=RESCO_REVISION,
        model="Pressure and MPC successive halving followed by independent validation",
        seed=[s for s, v in TRAIN] + [s for s, v in VALIDATION],
        split={"tuning": TRAIN, "validation": VALIDATION, "test": "Never used for selection"},
        metrics={
            "tuning_scores": training["tuning_scores"],
            "validation_controllers": aggregate(validation),
        },
        scope="All evaluated configurations and promotion decisions are retained.",
        results={"training": training, "validation": validation},
    )
