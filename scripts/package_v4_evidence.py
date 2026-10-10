"""Publish real experiment archives and exact source snapshots; omit data/model caches."""

import gzip
import hashlib
import json
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    out = Path("artifacts/cities/v4")
    raw_root = Path("data/learned-control-v4")
    files = sorted(raw_root.glob("*.json.gz"))
    if len(files) != 140:
        raise ValueError("Need all 40 training and 100 actual evaluation episodes")
    archive = out / "cooperative-q-episodes.zip"
    index = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in files:
            encoded = path.read_bytes()
            raw = gzip.decompress(encoded)
            record = json.loads(raw)
            bundle.writestr(path.name, encoded)
            index.append(
                {
                    "member": path.name,
                    "sha256": digest(encoded),
                    "uncompressed_sha256": digest(raw),
                    "compressed_bytes": len(encoded),
                    "raw_bytes": len(raw),
                    "city": record["city"],
                    "seed": record["seed"],
                    "controller_sha256": record["controller_sha256"],
                    "harness_sha256": record["harness_sha256"],
                }
            )
    (out / "cooperative-q-archives.json").write_text(
        json.dumps(
            {
                "archive": archive.name,
                "sha256": digest(archive.read_bytes()),
                "episodes": index,
                "scope": "Actual SUMO outputs, including all predeclared training and held-out policy episodes. No camera images, model weights or raw external datasets.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    training_input = Path("data/control-v4/transitions-dev.json").read_bytes()
    (out / "surrogate-training.json.gz").write_bytes(gzip.compress(training_input, mtime=0))
    sources = [
        "backend/atlas/city_forecast_v4.py",
        "backend/atlas/learned_control_v4.py",
        "scripts/evaluate_city_forecast_v4.py",
        "scripts/evaluate_cv_v4.py",
        "scripts/evaluate_learned_control_v4.py",
        "scripts/evaluate_surrogate_v4.py",
        "backend/atlas/evaluation/network_v4.py",
        "scripts/recover_v4_telemetry.py",
        "backend/atlas/evaluation/network_v4_runtime.py",
    ]
    source_dir = out / "research-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in sources:
        raw = Path(name).read_bytes()
        target = source_dir / Path(name).name
        target.write_bytes(raw)
        entries.append(
            {"path": name, "archive": target.relative_to(out).as_posix(), "sha256": digest(raw)}
        )
    (out / "research-source.json").write_text(
        json.dumps({"sources": entries}, indent=2), encoding="utf-8"
    )
    diagnostic_prefixes = (
        "control-v4-dev-screen-",
        "control-v4-dev-screen-corrected-",
        "control-v4-development-grid-",
        "control-v4-transition-training-",
    )
    diagnostics = sorted(
        path
        for path in Path("data/control-v4/raw").glob("*.json.gz")
        if path.name.startswith(diagnostic_prefixes)
    )
    diagnostic_archive = out / "controller-rejected-diagnostics.zip"
    diagnostic_index = []
    with zipfile.ZipFile(diagnostic_archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in diagnostics:
            encoded = path.read_bytes()
            raw = gzip.decompress(encoded)
            bundle.writestr(path.name, encoded)
            diagnostic_index.append(
                {"member": path.name, "sha256": digest(encoded), "raw_sha256": digest(raw)}
            )
    (out / "controller-rejected-diagnostics.json").write_text(
        json.dumps(
            {
                "archive": diagnostic_archive.name,
                "sha256": digest(diagnostic_archive.read_bytes()),
                "episodes": diagnostic_index,
                "scope": "All retained preliminary development, rejected screens and surrogate input runs. Early screens include an implementation diagnostic subsequently corrected before frozen final selection; not promoted results or additional independent held-out evidence.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "Packaged",
        len(files),
        "actual episodes, surrogate inputs and exact research source snapshots",
    )


if __name__ == "__main__":
    main()
