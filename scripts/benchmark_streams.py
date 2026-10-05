"""Progressive actual CPU inference runs, using process isolation like the runtime pool."""

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from atlas import config, db
from atlas.api import register_video
from atlas.experiments import save
from atlas.pipeline import process_video
from atlas.schemas import CameraConfig


def main(path, camera):
    db.init()
    settings = CameraConfig.model_validate_json(camera.read_text())
    scenarios = []
    for streams in [1, 2]:
        ids = [register_video(path.resolve(), path.name, "demo") for _ in range(streams)]
        with db.connection() as conn:
            for video_id in ids:
                conn.execute(
                    "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
                    (settings.model_dump_json(), video_id),
                )
        start = time.perf_counter()
        with ProcessPoolExecutor(max_workers=streams) as pool:
            outputs = list(pool.map(process_video, ids))
        elapsed = time.perf_counter() - start
        total_frames = sum(r["performance"]["processed_frames"] for r in outputs)
        scenarios.append(
            {
                "concurrent_streams": streams,
                "total_frames": total_frames,
                "wall_seconds": elapsed,
                "aggregate_fps": total_frames / elapsed,
                "runs": [r["performance"] for r in outputs],
            }
        )
        print(f"{streams} streams: {total_frames / elapsed:.2f} aggregate sampled FPS")
    save(
        "streams",
        {
            "scope": "Actual concurrent CPU inference on the same attributed demo; process startup included",
            "device": config.DEVICE,
            "scenarios": scenarios,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--camera", type=Path, default=config.ROOT / "docs" / "demo-camera.json")
    args = parser.parse_args()
    main(args.path, args.camera)
