"""Wrap retained measurements without rerunning or changing their dates."""

import json

from atlas import config
from atlas.evaluation.artifacts import BenchmarkArtifact

SOURCES = {
    "risk": (
        "risk",
        "synthetic",
        "ATLAS generated accelerated conflict scenarios",
        "seeded-v1",
        "Logistic regression / HistGradientBoosting",
    ),
    "forecast": (
        "forecasting",
        "synthetic",
        "ATLAS generated diurnal traffic",
        "seed-4444-v1",
        "HistGradientBoosting / statistical baselines",
    ),
    "simulation": (
        "signal_control",
        "controlled",
        "ATLAS seeded four-approach arrivals",
        "portable-v1",
        "Fixed / adaptive / constrained search",
    ),
    "sumo": (
        "signal_control",
        "controlled",
        "ATLAS seeded straight-through demand",
        "SUMO-1.27.1",
        "Fixed / portable-search split",
    ),
    "pipeline": (
        "systems",
        "real",
        "Mixkit Guadalajara #1755",
        "source-sha-in-results",
        "YOLOv8n-VisDrone + ByteTrack",
    ),
    "streams": (
        "systems",
        "real",
        "Mixkit Guadalajara #1755",
        "source-sha-in-pipeline",
        "Concurrent aerial production inference",
    ),
    "load": (
        "systems",
        "controlled",
        "Local mixed HTTP/SQLite requests",
        "load-v1",
        "FastAPI + SQLite WAL",
    ),
    "cv": (
        "detection_integration",
        "controlled",
        "COCO8 four validation images",
        "Ultralytics COCO8",
        "YOLO11n",
    ),
    "tracking-metric-validation": (
        "tracking_metric_fixture",
        "controlled",
        "Analytic MOT fixture",
        "fixture-v1",
        "TrackEval",
    ),
    "live-verification": (
        "integration",
        "real",
        "Mixkit Guadalajara #1755",
        "source-sha-in-pipeline",
        "HTTP upload + production aerial inference",
    ),
}


def main():
    target = config.ARTIFACTS / "benchmarks"
    target.mkdir(exist_ok=True)
    for name, (kind, provenance, dataset, revision, model) in SOURCES.items():
        path = config.ARTIFACTS / f"{name}.json"
        if not path.exists():
            continue
        old = json.loads(path.read_text(encoding="utf-8-sig"))
        item = BenchmarkArtifact(
            benchmark_type=kind,
            data_provenance=provenance,
            dataset=dataset,
            dataset_version=revision,
            model=model,
            date=old["generated_at"],
            hardware={
                **old.get("environment", {}),
                "ram_gb": None,
                "note": "Original recorded environment; RAM was not measured",
            },
            split=old.get("split", old.get("splits", {"seeds": old.get("seeds")})),
            seed=old.get("seed", old.get("seeds")),
            metrics={
                k: v for k, v in old.items() if k not in {"generated_at", "environment", "scope"}
            },
            scope=old["scope"],
            methodology={
                "source_artifact": f"artifacts/{name}.json",
                "adapter": "Metadata normalization only; no new measurement",
            },
        )
        (target / f"original_{name.replace('-', '_')}.json").write_text(
            item.model_dump_json(indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
