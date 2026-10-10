"""Generate measured v4 results and role bullets without choosing favorable test models."""

import json
from pathlib import Path


def read(name):
    return json.loads((Path("artifacts/cities/v4") / name).read_text(encoding="utf-8"))


def generate():
    data = read("data-index.json")
    forecast = read("city-forecast.json")
    perception = read("perception.json")
    total = sum(c["records"] for c in data["cities"])
    lines = [
        "# ATLAS 4.0 measured results",
        "",
        "Generated from recorded experiment artifacts by `python scripts/generate_v4_metrics.py`. This does not execute benchmarks. Original results and the [3.0 ledger](atlas-3-status.md) remain preserved. No new candidate is automatically promoted.",
        "",
        "## Official city counts and chronological forecasting",
        "",
        f"Five official adapters acquired **{total:,} real historical count bins**. Separate observation dates define training, validation and test periods. Three contiguous causal bins are required; missing bins remain missing. [Source provenance and licensing](atlas-4-data.md) · [Frozen protocol](city-forecast-v4-protocol.json) · [Actual results](../artifacts/cities/v4/city-forecast.json).",
        "",
        "| City | Validation-selected model | Test examples | Native interval | Test MAE | Persistence MAE | MAE reduction | 90% interval coverage |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    bullets = [
        "# ATLAS 4.0 evidence-backed resume candidates",
        "",
        "Retain the earlier [role bullets](RESUME_BULLETS.md) and historical Cologne, highway-GNN and complete CPU pipeline results. New city-count and CV experiments have distinct domains and costs.",
        "",
        "## Software engineering",
        "",
        f"- Built provenance-aware traffic-count ingestion across five official city sources, preserving {total:,} historical measurement bins with digest-checked caching, bounded retrieval, source-local timestamps and missing-data safeguards.",
        "  - Evidence: data-index.json and five compressed licensed aggregate archives; one-time source checks, not continuous availability.",
        "",
        "## Machine learning engineering",
        "",
    ]
    for city in forecast["cities"]:
        if city["status"] != "evaluated":
            lines.append(f"| {city['city']} | Insufficient data | — | — | — | — | — | — |")
            continue
        selected = next(m for m in city["models"] if m["name"] == city["validation_selected"])
        persistence = next(m for m in city["models"] if m["name"] == "persistence")
        score, base = (
            selected["test"]["mae_count_per_native_interval"],
            persistence["test"]["mae_count_per_native_interval"],
        )
        gain = 100 * (1 - score / base)
        interval = "/".join(str(v // 60) for v in selected["test"]["interval_seconds"])
        coverage = city["uncertainty"]["test_coverage"]
        lines.append(
            f"| {city['city'].title()} | {city['validation_selected']} | {selected['test']['examples']:,} | {interval} min | {score:.3f} | {base:.3f} | {gain:+.2f}% | {coverage * 100:.2f}% |"
        )
        if gain > 0:
            bullets.extend(
                [
                    f"- Reduced held-out {city['city'].title()} {interval}-minute count forecasting MAE by {gain:.2f}% versus persistence ({score:.3f} versus {base:.3f} vehicles/bin) on {selected['test']['examples']:,} chronological test examples using validation-selected {city['validation_selected'].replace('_', ' ')}.",
                    "  - Evidence: city-forecast.json; observational source counts, single training seed, not city queue accuracy or realized traffic savings.",
                ]
            )
    lines += [
        "",
        "Toronto and London test regressions are retained even though their models won validation. The geographic message network is a learned one-hop proximity model, not a surveyed directed road graph. Its contribution is compared with a matched local MLP in every city; it is not consistently superior. Austin's discontinued vision counters are not independently audited count truth. London has few irregular hourly survey observations. Marginal conformal intervals use validation residuals; temporal shift can violate exchangeability.",
        "",
        "## Strict four-city zero-shot transfer",
        "",
        "Every rotation trains on only the other four cities, including normalization and epoch selection. No target-city calibration is substituted for zero-shot inference.",
        "",
        "| Held-out city | Test MAE | Persistence MAE | MAE reduction | Target-city fit examples |",
        "|---|---:|---:|---:|---:|",
    ]
    for transfer in forecast["leave_one_city_out"]:
        if transfer["status"] != "evaluated_zero_shot":
            continue
        score, base = (
            transfer["test"]["mae_count_per_native_interval"],
            transfer["persistence"]["mae_count_per_native_interval"],
        )
        lines.append(
            f"| {transfer['held_out_city'].title()} | {score:.3f} | {base:.3f} | {100 * (1 - score / base):+.2f}% | {transfer['target_city_fit_examples']} |"
        )
    lines += [
        "",
        "Transfer failures prevent an operational promotion. Different source years and native intervals do not become simultaneous multimodal observations. All five SUMO twins remain exploratory: surveyed approaches, historical geometry, field queue/travel-time truth and municipal timing are not independently validated.",
        "",
        "## Continuous-video perception",
        "",
        "All three candidates process output for the same 4,260 complete UA-DETRAC frames. ByteTrack reproduces the preserved historical IDF1/HOTA exactly. Adaptive skipped frames hold the previous measured boxes; they are not newly detected trajectories. [Registered protocol](cv-v4-protocol.json) · [Actual per-camera/gate/cost records](../artifacts/cities/v4/perception.json).",
        "",
        "| Candidate | IDF1 | HOTA | ID switches | Fragmentation | Visible-count MAE | Process CPU seconds | Actual inference frames |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in perception["rows"]:
        m = row["metrics"]
        lines.append(
            f"| {row['candidate']} | {m['IDF1']:.6f} | {m['HOTA']:.6f} | {m['IDSW']:.0f} | {m['Frag']:.0f} | {m['visible_vehicle_count_mae']:.6f} | {m['process_cpu_seconds']:.3f} | {m['inferred_frames']:,} |"
        )
    baseline = next(r["metrics"] for r in perception["rows"] if r["candidate"] == "bytetrack_full")
    bot = next(r["metrics"] for r in perception["rows"] if r["candidate"] == "botsort_full")
    lines += [
        "",
        "BoT-SORT improves tracking accuracy but increases measured process CPU cost. Adaptive sampling reduces inference calls but does not establish lower CPU cost and reduces HOTA. No default changes. These are tracker-stage experiments on the reused historical holdout; the original 29.4 FPS refers to the unchanged complete ByteTrack pipeline. Ultralytics overrides the requested initial four-thread setting during CPU device setup; a separate same-path runtime probe observes eight threads. Wall timings share the development host and do not establish an isolated speedup. No independently annotated physical queue, natural-weather or five-city tracking score is inferred.",
    ]
    bullets += [
        "",
        "## Computer vision engineering",
        "",
        f"- Evaluated BoT-SORT against ByteTrack on {bot['frames']:,} independently annotated traffic frames, improving IDF1 from {baseline['IDF1']:.3f} to {bot['IDF1']:.3f} and HOTA from {baseline['HOTA']:.3f} to {bot['HOTA']:.3f}, with identity switches falling from {baseline['IDSW']:.0f} to {bot['IDSW']:.0f}.",
        "  - Evidence: perception.json; three reused UA-DETRAC sequences; higher CPU cost, optional candidate only; no new full-pipeline FPS claim.",
    ]
    profile_path = Path("artifacts/cities/v4/controller-profile.json")
    if profile_path.exists():
        profile = read("controller-profile.json")
        lines += [
            "",
            "## Controller and simulator research",
            "",
            "[Planner profile](../artifacts/cities/v4/controller-profile.json), [actual simulator equivalence](../artifacts/cities/v4/subscription-equivalence.json), frozen development/validation/final cohorts and cooperative-Q results are separate from city field validation. Exact historical traffic outcomes and modeled safety are preserved. Final cohort conclusions belong to the completed control report.",
            "",
            f"On {profile['samples']:,} matched synthetic decision snapshots, {profile['actions_match']:,} actions agree. Planner p95 falls from {profile['policies']['original_mpc']['p95_ms']:.3f} to {profile['policies']['cached_mpc']['p95_ms']:.3f} ms ({100 * (1 - profile['policies']['cached_mpc']['p95_ms'] / profile['policies']['original_mpc']['p95_ms']):.2f}% lower). This excludes SUMO and HTTP; shared-process RSS does not establish memory savings.",
        ]
        bullets += [
            "",
            f"- Vectorized and cached safety-gated MPC beam search, preserving {profile['actions_match']:,}/{profile['samples']:,} matched actions while reducing observed planner p95 from {profile['policies']['original_mpc']['p95_ms']:.3f} to {profile['policies']['cached_mpc']['p95_ms']:.3f} ms ({100 * (1 - profile['policies']['cached_mpc']['p95_ms'] / profile['policies']['original_mpc']['p95_ms']):.2f}%) on synthetic eight-phase snapshots.",
            "  - Evidence: controller-profile.json; actual artifact values, shared development host; excludes simulator/API and does not imply better traffic outcomes.",
        ]
    control_path = Path("artifacts/cities/v4/controller-results.json")
    if control_path.exists():
        control = read("controller-results.json")
        lines += [
            "",
            f"Completed **{control['deterministic_heldout_episodes']:,} deterministic held-out SUMO episodes**: five cities, three generated-demand regimes, twenty paired seeds, six controllers. Cached MPC preserves original traffic outcomes. Reductions below are means of paired seed percentages, with 95% bootstrap intervals; positive means less delay. These are exploratory, uncalibrated OSM corridors, not field savings.",
            "",
        ]
        for regime, cities in control["demand_regimes"].items():
            lines += [
                f"### {regime.title()} generated demand",
                "",
                "| City | Cached/original delay | Reduction vs fixed (95% CI) | Reduction vs max-pressure (95% CI) |",
                "|---|---:|---:|---:|",
            ]
            for city in cities:
                fixed = next(c for c in city["comparisons"] if c["baseline"] == "fixed")
                pressure = next(c for c in city["comparisons"] if c["baseline"] == "max_pressure")

                def cell(result):
                    return f"{result['mean_paired_reduction_pct']:+.2f}% [{result['ci95'][0]:+.2f}, {result['ci95'][1]:+.2f}]"

                lines.append(
                    f"| {city['city'].title()} | {city['metrics']['mean_delay_s']:.3f} s | {cell(fixed)} | {cell(pressure)} |"
                )
            lines.append("")
        lines += [
            "High-demand Seattle loses to max-pressure; high-demand Toronto and low-demand Toronto have inconclusive pressure comparisons. Nominal Calgary's fixed-time confidence interval crosses zero. No universal superiority is claimed.",
            "",
            "### Cooperative multi-agent zero-shot research",
            "",
            "A shared tabular cooperative policy trains on four cities per rotation, then freezes before testing the fifth. Forty 300-second training episodes and one hundred nominal held-out episodes execute actual SUMO; every action passes the independent modeled safety gate. Unseen states fall back to max-pressure. This is an experimental cooperative Q learner, not a deep graph MARL policy.",
            "",
            "| Held-out city | Delay | Reduction vs fixed | Reduction vs max-pressure | Reduction vs original (95% CI) |",
            "|---|---:|---:|---:|---:|",
        ]
        for city in control["cooperative_q_zero_shot"]:
            c = city["comparisons"]
            original = c["original_mpc"]
            lines.append(
                f"| {city['city'].title()} | {city['mean_delay_s']:.3f} s | {c['fixed']['mean_paired_reduction_pct']:+.2f}% | {c['max_pressure']['mean_paired_reduction_pct']:+.2f}% | {original['mean_paired_reduction_pct']:+.2f}% [{original['reduction_ci95'][0]:+.2f}, {original['reduction_ci95'][1]:+.2f}] |"
            )
        lines += [
            "",
            "Toronto and London regress; no policy promotion. Learned-policy low/high robustness is unmeasured. All one hundred modeled safety counts are zero; this is not a physical certification. [Complete comparisons](../artifacts/cities/v4/controller-results.json) and lossless archives include every run. One Austin high-demand actuated attempt encountered non-finite geographic replay coordinates; an isolated serialization-only recovery reran the unchanged seed and frozen physics, retained finite metrics, and explicitly marked two coordinates unavailable. [Failure and recovery record](../artifacts/cities/v4/controller-telemetry-recovery.json).",
            "",
        ]
        gains = [
            f"{c['city'].title()} {c['comparisons']['original_mpc']['mean_paired_reduction_pct']:.2f}%"
            for c in control["cooperative_q_zero_shot"]
            if c["comparisons"]["original_mpc"]["mean_paired_reduction_pct"] > 0
        ]
        regressions = [
            c["city"].title()
            for c in control["cooperative_q_zero_shot"]
            if c["comparisons"]["original_mpc"]["mean_paired_reduction_pct"] < 0
        ]
        bullets += [
            "",
            f"- Built {len(control['cooperative_q_zero_shot'])} frozen four-city cooperative-control rotations and evaluated {sum(c['seeds'] for c in control['cooperative_q_zero_shot'])} zero-shot SUMO episodes; nominal delay reductions versus frozen MPC: {', '.join(gains)}; {', '.join(regressions)} regressed.",
            "  - Evidence: controller-results.json; 20 paired seeds per city, generated demand, no automatic promotion or municipal savings claim.",
        ]
    ux_path = Path("artifacts/cities/v4/ux-performance.json")
    if ux_path.exists():
        ux = read("ux-performance.json")
        lines += [
            "",
            "## Actual browser and native API verification",
            "",
            f"Local production browser evidence includes {len(ux['comparisons'])} matched route/viewport observations and {len(ux['accessibility']['scans'])} automated accessibility scans. Timing is one sample per route, not a field Core Web Vitals or human task study. [Raw observations](../artifacts/cities/v4/ux-performance.json).",
            "",
            "| Landing viewport | Before transferred bytes | After transferred bytes | Observed reduction |",
            "|---|---:|---:|---:|",
        ]
        for row in ux["comparisons"]:
            if row["route"] == "/":
                lines.append(
                    f"| {row['width']} px | {row['before_transfer_bytes']:,} | {row['after_transfer_bytes']:,} | {row['observed_transfer_reduction_percent']:.2f}% |"
                )
        lines += [
            "",
            "Authenticated native count inference reproduces each first chronological test prediction; 250 repeated warm HTTP requests cover all five frozen models. Unauthorized requests are rejected and snapshot stock is refused as measured flow. This is a warm local latency check, not concurrent service throughput. [Actual profiles](../artifacts/cities/v4/city-runtime-profile.json).",
        ]
    surrogate_path = Path("artifacts/cities/v4/surrogate.json")
    if surrogate_path.exists():
        lines += [
            "",
            "The learned five-second observed-policy queue surrogate loses to queue persistence in all five held-out cities. It is not used to replace SUMO truth or rank unsupported counterfactual plans. [All surrogate failures](../artifacts/cities/v4/surrogate.json).",
        ]
    bullets += [
        "",
        "## Applied AI / research",
        "",
        "- Implemented reproducible chronological five-city forecasting and five strict leave-one-city-out rotations, with validation-selected models, test-day paired uncertainty, interval coverage, drift flags and preserved transfer regressions.",
        "  - Evidence: city-forecast.json; highway benchmarks remain separate, no automatic promotion.",
        "",
        "## Infrastructure / performance",
        "",
        "- Built authenticated city-count inference with checksum-pinned local checkpoints, weights-only neural loading, causal cadence/domain validation, bounded caches and explicit shadow-versus-persistence monitoring.",
        "  - Evidence: city-runtime-profile.json and runtime behavior tests; same-input local HTTP probes are not a sustained production SLA.",
        "",
    ]
    return "\n".join(lines) + "\n", "\n".join(bullets) + "\n"


if __name__ == "__main__":
    results, bullets = generate()
    Path("docs/atlas-4-results.md").write_text(results, encoding="utf-8")
    Path("docs/atlas-4-resume-bullets.md").write_text(bullets, encoding="utf-8")
    print("Generated actual city, CV, transfer results and qualified role bullets")
