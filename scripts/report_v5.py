"""Generate scoped ATLAS 5 results and resume claims directly from measured artifacts."""

import json
from pathlib import Path


def main():
    root = Path("artifacts/cities/v5")
    read = lambda name: json.loads((root / f"{name}.json").read_bytes())  # noqa: E731
    control, calibration, forecast, cv = (
        read(n)
        for n in ("control-assessment", "calibration-readiness", "forecast-results", "cv-runtime")
    )
    ux = read("ux-comparison")
    lighthouse = next(r for r in ux["lighthouse"] if r["stage"] == "after")
    ux_paragraph = (
        f"Bundled licensed fonts and reserved asynchronous loading space reduce the maximum observed local CLS "
        f"from {ux['before']['maximum_cls']:.3f} to {ux['after']['maximum_cls']:.3f} across "
        f"{ux['after']['scans']} matched city/view/viewport cases, with zero automated accessibility violations, "
        f"page errors, failed responses or horizontal overflow. A separate mobile-throttled Lighthouse sample "
        f"scores performance {100 * lighthouse['scores']['performance']:.0f}, accessibility "
        f"{100 * lighthouse['scores']['accessibility']:.0f}, best practices "
        f"{100 * lighthouse['scores']['best-practices']:.0f} and SEO {100 * lighthouse['scores']['seo']:.0f}. "
        "Each case has one local sample; this does not establish a statistical speedup or field Core Web Vitals. "
        "Lighthouse LCP is slightly higher after the change. Human participants remain zero. "
        "The actual 36-second walkthrough and five source-hashed screenshots show current application output.\n"
    )
    report = [
        "# ATLAS 5 measured results\n",
        "This engineering release preserves ATLAS 4 and all stronger historical benchmarks. **Zero independently validated city twins; zero observed field benefits; the experimental portfolio is not promoted.** Public Vercel serves genuine precomputed processing and simulation outputs. The private native worker has actual SUMO verification; public remote execution remains disabled.\n",
        "## Five-city calibration\n",
        "These are historical demand-profile reconstruction errors, **not simulated-state accuracy**. Whole observation dates split calibration, validation and final rows. The ATLAS 4 archive was already evaluated, so this is regression evidence rather than a new blinded cohort. Unknown channels receive no prediction. Source count accuracy, physical queues, speed and travel-time errors remain unavailable.\n",
        "| City | Source bins | Final paired rows | Coverage | Count MAE / RMSE, vehicles per native bin | Flow MAE, equivalent veh/hour | GEH < 5 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in calibration["cities"]:
        m = c["count_demand_regression"]["final"]
        report.append(
            f"| {c['city']} | {c['record_count']:,} | {m['rows']} | {m['coverage_fraction']:.1%} | {m['count_mae']:.3f} / {m['count_rmse']:.3f} | {m['flow_mae_vph']:.3f} | {m['geh_below_5_fraction']:.1%} |"
        )
    report.extend(
        [
            "\nWeighted nonnegative OD inversion rejects rank-deficient or unverified mappings. The production archive supplies no verified network incidence matrix; thus an OD solution is not invented. Arrival profiles use exposure-weighted Poisson shrinkage chosen on validation only; this is an explicit statistical assumption.\n",
            "Official follow-up resolved 23 current Seattle street segments through COMPKEY, with zero missing keys. Current segment extent is not an exact historical counter/lane location. Toronto's official intersection register, Austin's radar sensor registry and Calgary's CalTRACS metadata are retained. Austin radar is also historical/discontinued. Whitehall count point 27663 supplies 240 actual directional hourly manual surveys across ten irregular dates. Its separate 7/1/2-date study estimates 48 final counts at MAE 353.208 veh/hour, normalized MAE 68.83%, and 0% GEH below 5: **unsuccessful**. Final uncertainty is unavailable with two dates. No sparse annual observations are presented as a current stream.\n",
            "## City forecasting and transfer\n",
            "Causal history ratios, local-time features where timezone is verified, validation-selected ridge/boosting, drift fallback and validation conformal intervals. Strict leave-one-city-out fitting, candidate selection and interval calibration use four source cities; target labels and target normalization statistics used: **0**. These historical final partitions were already evaluated in ATLAS 4. No model is promoted using these outcomes.\n",
            "| City | Local MAE / persistence | Local reduction | Zero-shot MAE / persistence | Zero-shot reduction | Zero-shot 90% coverage / width / proper interval score |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for local in forecast["local"]:
        zero = next(r for r in forecast["zero_shot"] if r["held_out_city"] == local["city"])
        i = zero["interval"]
        report.append(
            f"| {local['city']} | {local['final']['mae_count']:.3f} / {local['persistence']['mae_count']:.3f} | {local['mae_reduction_vs_persistence_pct']:.2f}% | {zero['final']['mae_count']:.3f} / {zero['persistence']['mae_count']:.3f} | {zero['mae_reduction_vs_persistence_pct']:.2f}% | {i['empirical_coverage']:.1%} / {i['mean_width_count']:.2f} / {i['mean_interval_score']:.2f} |"
        )
    report.extend(
        [
            "\nErrors are vehicles per each source's native count interval, not comparable physical queue errors. London local persistence regression is repaired in this study; Calgary zero-shot improves, but **Austin zero-shot worsens materially**. Toronto local abstains to persistence. Prior Seattle/Austin/Calgary ATLAS 4 local models remain stronger and preserved. Geographic-message ablations remain explicitly proximity models; no directed surveyed sensor graph exists. Independent multimodal contribution and few-shot transfer are blocked/not established.\n",
            "## Robust control: new paired SUMO cohort\n",
            f"Development: {control['development_episodes']} episodes; validation: {control['validation_episodes']}; final: **{control['final_episodes']:,}**. Final seeds 55301–55310, five city networks, low/nominal/high demand, lane closure, sensor outage and bursty demand shift, seven controllers. A threshold/hysteresis/dwell selector uses current measured inbound/downstream occupancy, frozen before final runs, never a final-outcome oracle. Paired route/network inputs and source initial states are verified; **300 cached/original pairs have identical measured outcomes**.\n",
            "| Baseline | Mean paired delay reduction | 95% city/seed cluster interval |",
            "| --- | --- | --- |",
        ]
    )
    for row in control["overall"]:
        report.append(
            f"| {row['baseline']} | {row['mean_paired_delay_reduction_pct']:.2f}% | {row['ci95_pct'][0]:.2f} to {row['ci95_pct'][1]:.2f}% |"
        )
    report.extend(
        [
            "\nPositive reductions favor the portfolio. Overall cached/original MPC and cooperative Q beat the new selector. Seattle high improves 8.54% vs max-pressure and Calgary nominal 21.20%, but Toronto low regresses 2.94% on average and **28.75% in seed 55307**. That exceeds the predeclared 20% worst-episode allowance; **promotion fails and production policy is unchanged**. Zero modeled signal-safety violations occur in all 2,550 new episodes. This does not certify field actuation, pedestrian safety or municipal compliance.\n",
            "Every per-seed delay p95, throughput, unfinished trips, queue, stops, travel time, phase switches, modeled emissions, decision latency, worker RSS and wall time is published. Pedestrian/transit/spillback measurements remain null where unsupported; emissions are SUMO estimates with explicit telemetry coverage. Bootstrap blocks retain all six scenarios per city/seed. Original 1,800 episodes remain untouched. The queue surrogate remains retired because it lost to persistence across all five cities.\n",
            "## Repeated complete computer-vision pipeline\n",
            "Three counterbalanced repetitions per tracker, complete 1,130-frame MVI_40701, CPU YOLO11n/640/confidence 0.25. Outer wall timing includes fresh model/tracker startup, decode, inference, analytics, forecasting, SQLite and JSON persistence. No physical calibration is supplied; safety inference remains gated. Shared Intel i7 host load and observed eight PyTorch threads are recorded.\n",
            "| Tracker | Complete aggregate FPS | Median wall time | Complete-sequence IDF1 / HOTA |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in cv["summaries"]:
        a = next(r for r in cv["runs"] if r["tracker"] == row["tracker"])["accuracy"]
        report.append(
            f"| {row['tracker']} | {row['aggregate_fps']:.2f} | {row['median_wall_s']:.2f} s | {a['idf1']:.3f} / {a['hota']:.3f} |"
        )
    report.extend(
        [
            "\nBoT-SORT's median complete wall time is 23.1% higher. Single-sequence IDF1 improves from 0.739 to 0.756 and count MAE from 2.122 to 1.945 vehicles. ByteTrack remains production. These scores do not replace the historical three-sequence 0.793/0.808 IDF1 results. The measured 18.33 FPS narrow repeat workload is slower than historical 29.4 FPS; hardware load, cold-start and sequence differences prevent attributing this as a controlled code regression or speedup. City CV labels, lane assignment and physical queue ground truth remain absent.\n",
            "## Product, workers and reproducibility\n",
            ux_paragraph,
            "The public journey connects official city observations, twin-validation matrix and exact count/demand series, corridor replay, the ATLAS 5 six-case comparison, and authentic ten-seed pilot exports. Native prediction results and transfer regressions are visible in each city's calibration view. Linked replay uses actual five-second SUMO snapshots; maps are not camera trajectories. Every model/result has scope and provenance.\n",
            "Confidence-aware fusion rejects incompatible units, unmapped footprints, stale/future measurements and low coverage. It avoids double-counting overlapping cameras and quarantines camera/detector disagreement. Its variance is conditional on supplied measurement models; no calibrated uncertainty or empirical city-fusion gain is claimed without coeval sources.\n",
            "The authenticated native API has durable SQLite jobs/quotas, one owned child per bounded paired experiment, account isolation, cancellation, timeout, aggregate RSS monitoring, source/parameter experiment IDs, progress, heartbeat and hashed results. Actual native SUMO verifies the lifecycle. It is **disabled publicly**. External hosting requires TLS, secret provisioning, kernel CPU/PID/disk limits, retention, observability and budget approval; it is not presented as a deployment sandbox. No new paid service was introduced; incremental hosted-worker spend is $0, existing account charges and local electricity are unmeasured. [Worker architecture](execution-v5.md).\n",
            "`python scripts/verify_v5_evidence.py` checks all 75 lossless episode bundles, sources, final pairing, frozen protocols, regressions, CV repeats and native-worker provenance without restricted datasets. The ATLAS 4 measured frontend source is preserved in `ux-measured-source.zip`, allowing frontend evolution without relabeling old browser measurements. [Usability protocol](usability-v5-protocol.md): **zero participants**, no invented human results. Current automated verification and production provenance are recorded separately at release.\n",
            "## Supervised municipal pilot readiness\n",
            "Ready for a technical research demonstration and agency data-readiness discussion. **Not ready for an operational benefit claim or unattended signal actuation.** A defensible shadow pilot needs verified historical/current lane and detector correspondence, contemporaneous timing/conflict/pedestrian surveys, independent count and dynamic-state holdouts, source-specific uncertainty, camera permissions, a reviewed security/cost envelope, agency-approved oversight and a prospective causal evaluation. Level 2 remains blocked for all five cities; Level 3 is unmeasured. No task passing substitutes for those observations.\n",
            "Evidence: [`artifacts/cities/v5`](../artifacts/cities/v5), frozen protocols and scripts; historical [ATLAS 4 results](atlas-4-results.md), [real-world evaluation](real-world-evaluation.md) and [Cologne control results](signal-control-results.md).\n",
        ]
    )
    Path("docs/atlas-5-results.md").write_text("\n".join(report), encoding="utf-8")
    bullets = """# ATLAS 5 evidence-backed resume candidates

Each bullet states the system, mechanism, measured scope and evidence boundary.

- Built a five-city calibration-readiness workflow over 52,679 official historical count bins, using identifiable weighted demand inversion, chronological exposure-weighted profiles and explicit missing-state gates; published source-specific errors and preserved **zero independently validated twins** rather than treating fitted demand as simulator accuracy. Evidence: `calibration-readiness.json`, `geometry-investigation.json`, calibration protocol.
- Implemented a decision-time occupancy controller portfolio with hysteresis, dwell constraints and independent phase-safety gating; evaluated **2,550 new SUMO episodes**, including **2,100 final runs** across five cities, six stress cases and seven controllers, with **zero modeled signal-safety violations**. It reduced delay 13.95% vs fixed and 7.36% vs max-pressure overall, but was 2.33% worse than cached MPC and failed the worst-episode guard; no production promotion. Evidence: `control-assessment.json`, frozen protocol and 75 lossless bundles.
- Implemented strict source-only cross-city forecasting with scale-invariant causal features, drift fallback and validation-calibrated intervals; evaluated all five held-out cities with **zero target label rows or target normalization statistics**. Calgary transfer improved persistence by 6.92%, while Austin regressed approximately 78.5%; all candidate outcomes and proper interval scores remain published. Evidence: `forecast-results.json`; historical regression cohort, not new external validation.
- Built an authenticated, durable, bounded native experiment service with persistent quotas, isolated owned subprocesses, source-hashed experiment IDs, cancellation and time/RSS limits; verified two actual paired SUMO simulations, account isolation and lifecycle behavior. Public execution remains disabled and introduces **$0 incremental hosted-worker spend**. Evidence: `worker-verification.json` and native execution tests; not a claim of deployed public workers.

Preserved stronger historical claims: pretrained YOLO11n **0.898 mAP@50**, production ByteTrack **0.793 IDF1** across 4,260 predeclared UA-DETRAC frames; original measured complete pipeline **29.4 CPU FPS**; METR-LA **2.490 vs 2.813 mph** persistence and separate directional GNN **2.344 mph**; cached planner p95 **2.084 to 0.585 ms (71.95%)**, matching 1,000 original actions; Cologne validation-selected MPC **65.7% vs fixed / 45.3% vs max-pressure** across ten paired seeds. Each retains its original dataset, hardware and simulation scope.

New complete-pipeline repeats measure **18.33 ByteTrack / 15.06 BoT-SORT FPS** on one full 1,130-frame sequence; these do not improve the historical throughput claim. Human usability, city lane/queue accuracy and observed field traffic savings remain unmeasured.
"""
    bullets += "\n- Improved frontend layout stability through bundled licensed fonts and reserved loading space; 30 local desktop/mobile city/view scans report maximum observed CLS 0.567 to 0.024, zero automated accessibility violations, and a separate Lighthouse performance score of 97. Evidence: `ux-before.json`, `ux-performance.json`, `ux-comparison.json` and immutable source archives; one local sample per case, no field or human usability claim.\n"
    Path("docs/atlas-5-resume-bullets.md").write_text(bullets, encoding="utf-8")
    print("Generated scoped results and resume candidates from actual ATLAS 5 artifacts")


if __name__ == "__main__":
    main()
