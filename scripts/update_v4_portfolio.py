"""Copy actual presentation assets and derive the city card metric from frozen evidence."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repository.resolve()
    remote = subprocess.check_output(
        ["git", "-C", str(repo), "remote", "get-url", "origin"], text=True
    ).strip()
    if remote.removesuffix(".git") != "https://github.com/youssef061204/YoussefElsokkary":
        raise ValueError("Existing intended portfolio repository required")
    forecast = json.loads(Path("artifacts/cities/v4/city-forecast.json").read_text())
    city = next(c for c in forecast["cities"] if c["city"] == "seattle")
    selected = next(m for m in city["models"] if m["name"] == city["validation_selected"])
    persistence = next(m for m in city["models"] if m["name"] == "persistence")
    actual = selected["test"]["mae_count_per_native_interval"]
    base = persistence["test"]["mae_count_per_native_interval"]
    metric = {
        "value": f"{100 * (1 - actual / base):.2f}%",
        "label": "Seattle count MAE vs persistence",
        "detail": f"{actual:.3f} vs {base:.3f} vehicles per 15-minute bin; {selected['test']['examples']:,} chronological test examples; validation-selected temporal MLP; source counts, not physical queue truth",
    }
    project_file = repo / "app/lib/projects.ts"
    source = project_file.read_text(encoding="utf-8")
    start, end = source.index('slug: "atlas"'), source.index('slug: "tradepersona"')
    block = source[start:end]
    block, changes = re.subn(
        r'\{\s*"?value"?\s*:\s*"(?:5\.85%|18\.94%)"\s*,\s*"?label"?\s*:\s*"(?:forecast MAE vs original ML|Seattle count MAE vs persistence)"\s*,\s*"?detail"?\s*:\s*"[^"\n]*"\s*\}',
        json.dumps(metric, ensure_ascii=False),
        block,
    )
    if changes != 1:
        raise ValueError("Expected one existing ATLAS forecast metric")
    project_file.write_text(source[:start] + block + source[end:], encoding="utf-8")
    media = repo / "public/projects/atlas"
    media.mkdir(parents=True, exist_ok=True)
    assets = {
        "five-city-command.jpg": "five-city-command.jpg",
        "cv-tracking.jpg": "cv-tracking-v4.jpg",
        "city-forecast.jpg": "city-forecast.jpg",
        "optimization.jpg": "optimization-v4.jpg",
        "laboratory.jpg": "laboratory-v4.jpg",
        "walkthrough.mp4": "walkthrough-v4.mp4",
    }
    for source_file, target in assets.items():
        shutil.copyfile(Path("artifacts/portfolio/v4") / source_file, media / target)
    shutil.copyfile("artifacts/portfolio/v4/provenance.json", media / "provenance-v4.json")
    provenance = {
        "metric": metric,
        "sources": {
            name: {
                "sha256": hashlib.sha256(Path(name).read_bytes()).hexdigest(),
                "url": "https://github.com/youssef061204/ATLAS/blob/main/" + name,
            }
            for name in (
                "artifacts/cities/v4/city-forecast.json",
                "artifacts/cities/v4/controller-profile.json",
                "artifacts/cities/v4/controller-results.json",
            )
        },
        "scope": "One city card metric derived from actual validation-selected chronological results; Toronto/London regressions retained in project details and linked complete report.",
    }
    (media / "evidence-v4.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print("Updated existing portfolio metric and copied six actual media assets")


if __name__ == "__main__":
    main()
