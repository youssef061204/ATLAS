"""Preserve exact ATLAS 6 sources before subsequent engineering changes."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "artifacts/reality/v6/source-baseline.zip"
    if destination.exists():
        raise SystemExit("Baseline already exists; never overwrite a historical snapshot")
    paths = set()
    for pattern in ("scripts/*v6*.py", "backend/atlas/*_v6.py", "docs/*v6*.json"):
        paths.update(ROOT.glob(pattern))
    paths.add(ROOT / "backend/atlas/pipeline.py")
    media = json.loads((ROOT / "artifacts/portfolio/v6/provenance.json").read_text())
    paths.update(ROOT / "frontend" / name for name in media["measured_source_sha256"])
    paths.add(ROOT / "frontend/components/reality-replay.module.css")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 10, 16, 6, 30, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(json.dumps({"files": len(paths), "sha256": digest, "bytes": destination.stat().st_size}))


if __name__ == "__main__":
    main()
