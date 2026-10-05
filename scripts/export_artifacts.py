"""Flatten generated numeric metrics to CSV and refresh measured resume bullets."""

import csv
import json
from pathlib import Path

from atlas import config

rows = []


def visit(prefix, value, scope):
    if isinstance(value, dict):
        for key, child in value.items():
            visit(f"{prefix}.{key}", child, scope)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            visit(f"{prefix}[{i}]", child, scope)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        rows.append({"metric": prefix, "value": value, "scope": scope})


for path in [*config.ARTIFACTS.glob("*.json"), *(config.ARTIFACTS / "benchmarks").glob("*.json")]:
    item = json.loads(path.read_text(encoding="utf-8-sig"))
    visit(
        str(path.relative_to(config.ARTIFACTS)),
        item.get("metrics", item),
        item.get("scope", "Generated experiment"),
    )
with (config.ARTIFACTS / "metrics.csv").open("w", newline="", encoding="utf-8") as output:
    writer = csv.DictWriter(output, fieldnames=["metric", "value", "scope"])
    writer.writeheader()
    writer.writerows(rows)

pipeline = json.loads((config.ARTIFACTS / "pipeline.json").read_text())
simulation = json.loads((config.ARTIFACTS / "simulation.json").read_text())
risk = json.loads((config.ARTIFACTS / "risk.json").read_text())
performance = pipeline["performance"]
score = risk["models"][risk["selected"]]
bullets = f"""# Measured resume bullets

- Built a local traffic digital twin with Next.js, Python, YOLOv8n-VisDrone, and ByteTrack; processed {performance["processed_frames"]} actual video frames at {performance["processed_fps"]:.1f} sampled FPS on CPU with {performance["inference_ms"]["p95"]:.0f} ms p95 detector/tracker latency and synchronized 3D replay.
- Reduced simulated mean vehicle delay by {simulation["mean_delay_reduction_pct"]:.1f}% against fixed timing across {len(simulation["seeds"])} held-out arrival seeds through constrained signal search, using identical demand and objectives that include unfinished queues and pedestrian wait.
- Evaluated logistic regression and gradient boosting for synthetic traffic-conflict screening, achieving {score["auroc"]:.3f} AUROC and {score["auprc"]:.3f} AUPRC on 3,000 independent generated test scenarios with validation-selected thresholds, Brier scoring, and calibration analysis.

These statements describe the measured hardware, simulation, and synthetic experiments—not traffic-domain accuracy, GPU performance, or field-trial safety improvements. Sources: `artifacts/pipeline.json`, `artifacts/simulation.json`, and `artifacts/risk.json`. Regenerate with `python scripts/export_artifacts.py` after new experiments.
"""
(Path("docs") / "resume-bullets.md").write_text(bullets, encoding="utf-8")
real = config.ARTIFACTS / "benchmarks"
if (real / "real_video_pipeline.json").exists():

    def read(name):
        return json.loads((real / f"{name}.json").read_text())["metrics"]

    system, detection, tracking, control = [
        read(name)
        for name in [
            "real_video_pipeline",
            "real_detection",
            "real_tracking",
            "realistic_signal_control",
        ]
    ]
    bullets = f"""# Verified resume bullets

- Built a traffic intelligence platform with synchronized video and 3D replay; processed {system["frames"]:,} actual annotated traffic frames at {system["pipeline_fps"]:.1f} FPS on an Intel i7 CPU, including inference, analytics, and persistence, with {system["inference_ms"]["p95"]:.1f} ms p95 detector/tracker latency.
- Evaluated pretrained YOLO11n and production ByteTrack on three complete UA-DETRAC test sequences, measuring {detection["map50"]:.3f} mAP@50 and {tracking["IDF1"]:.3f} IDF1; benchmarked causal forecasting on all 207 METR-LA sensors with chronological held-out evaluation.
- Developed constrained signal search yielding {simulation["mean_delay_reduction_pct"]:.1f}% lower simulated mean delay across three held-out synthetic seeds; audited four controllers over 12 held-out RESCO Cologne runs and identified {abs(control["mean_delay_reduction_pct"]):.1f}% higher ATLAS delay under the realistic demand shift.

Sources: `artifacts/benchmarks/real_video_pipeline.json`, `real_detection.json`, `real_tracking.json`, `real_forecasting.json`, `realistic_signal_control.json`, and `artifacts/simulation.json`. UA-DETRAC results cover a predeclared three-sequence subset, not the full challenge. RESCO is real-world-derived simulation; the 37.5% improvement is controlled synthetic evaluation. No field safety benefit or GPU performance is claimed. Regenerate with `python scripts/export_artifacts.py`.
"""
    (config.ROOT / "docs" / "resume-bullets.md").write_text(bullets, encoding="utf-8")
    if (real / "improved_signal_control.json").exists():
        improved = read("improved_signal_control")
        paired = improved["paired_comparisons"]
        if paired["fixed"]["paired_delay_reduction_ci95_s"][0] > 0:
            forecast = read("real_forecasting")["horizons"]["5"]
            new = improved["controllers"]["atlas_improved"]["mean_delay_s"]
            bullets = f"""# Verified resume bullets

- Built a traffic digital twin with synchronized video and 3D replay; processed {system["frames"]:,} real annotated traffic frames at {system["pipeline_fps"]:.1f} FPS on an Intel i7 CPU, including inference, analytics, and persistence.
- Evaluated pretrained YOLO11n and production ByteTrack on three complete UA-DETRAC test sequences, measuring {detection["map50"]:.3f} mAP@50 and {tracking["IDF1"]:.3f} IDF1; achieved {forecast["atlas_gradient_boosting"]["mae"]:.3f} mph five-minute METR-LA MAE versus {forecast["persistence"]["mae"]:.3f} persistence across all 207 sensors under chronological holdout.
- Replaced failed cyclic signal search with validation-selected, constraint-aware MPC, measuring {new["mean"]:.2f} s mean delay and {paired["fixed"]["mean_paired_improvement_pct"]:.1f}% paired reduction versus fixed timing ({paired["max_pressure"]["mean_paired_improvement_pct"]:.1f}% versus max-pressure) across {improved["runs_per_controller"]} unseen RESCO Cologne1 seeds with bootstrap confidence intervals and separate ablations.

Sources: `artifacts/benchmarks/real_video_pipeline.json`, `real_detection.json`, `real_tracking.json`, `real_forecasting.json`, and `improved_signal_control.json`. RESCO is real-world-derived simulation, not a field trial. The original 66.45 s failure remains published in `original_signal_control_failed.json`; untuned Ingolstadt1 transfer failed to beat either baseline. Forecast ablations show only a small, uncertain benefit. UA-DETRAC covers a predeclared subset, not the full challenge; GPU and field safety benefits are unmeasured. Regenerate with `python scripts/export_artifacts.py`.
"""
            (config.ROOT / "docs" / "resume-bullets.md").write_text(bullets, encoding="utf-8")
print(f"Exported {len(rows)} measured values to artifacts/metrics.csv")
