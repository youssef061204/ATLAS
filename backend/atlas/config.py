import os
from pathlib import Path

_source_root = Path(__file__).resolve().parents[2]
ROOT = Path(
    os.getenv(
        "ATLAS_ROOT",
        str(_source_root if (_source_root / "pyproject.toml").exists() else Path.cwd()),
    )
).resolve()
DATA = Path(os.getenv("ATLAS_DATA_DIR", str(ROOT / "data"))).resolve()
ARTIFACTS = ROOT / "artifacts"
MODEL = os.getenv("ATLAS_MODEL", "yolo11n.pt")
DEVICE = os.getenv("ATLAS_DEVICE", "cpu")
WORKERS = int(os.getenv("ATLAS_WORKERS", "1"))
MAX_UPLOAD = int(os.getenv("ATLAS_MAX_UPLOAD_MB", "250")) * 1024 * 1024
MAX_SECONDS = float(os.getenv("ATLAS_MAX_VIDEO_SECONDS", "1800"))
if WORKERS < 1 or WORKERS > 8 or MAX_UPLOAD <= 0 or MAX_SECONDS <= 0:
    raise ValueError("Invalid worker, upload, or video-duration configuration")
for directory in (DATA, DATA / "uploads", DATA / "results", ARTIFACTS):
    directory.mkdir(parents=True, exist_ok=True)
