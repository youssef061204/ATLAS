"""Temporarily inspect actual Caltrans HLS video pixels; delete all media on exit."""

import argparse
import json
import tempfile
import time
from pathlib import Path

import cv2
import httpx
from atlas.hls_v6 import playlist
from process_caltrans_live_v7 import INTEGRATION, ROOT, SOURCE, TERMS, fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--survey", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        if (
            "public domain" not in fetch(client, TERMS, 500000).decode()
            or "There is no charge" not in fetch(client, INTEGRATION, 500000).decode()
        ):
            raise ValueError("Reviewed source terms changed")
        sources = (
            [SOURCE]
            if not args.survey
            else [
                "https://wzmedia.dot.ca.gov/D12/NB5SR55.stream/playlist.m3u8",
                "https://wzmedia.dot.ca.gov/D12/NB5DisneylandDr.stream/playlist.m3u8",
            ]
        )
        with tempfile.TemporaryDirectory(
            prefix="atlas-visual-audit-", dir=ROOT / "data/reality-v7"
        ) as temporary:
            import numpy as np

            panels, summaries = [], []
            start = time.monotonic()
            for source in sources:
                parsed = playlist(fetch(client, source, 65536).decode(), source)
                if "variant" in parsed:
                    url = parsed["variant"]
                    parsed = playlist(fetch(client, url, 65536).decode(), url)
                video = Path(temporary) / "current.ts"
                video.write_bytes(fetch(client, parsed["segments"][-1]["url"], 8000000))
                capture = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
                frames = []
                for i in range(51):
                    ok, frame = capture.read()
                    if not ok:
                        raise ValueError("Insufficient actual consecutive video")
                    if i in [0, 50]:
                        frames.append(cv2.resize(frame, (768, 432)))
                capture.release()
                video.unlink()
                panel = np.hstack(frames)
                panels.append(panel)
                summaries.append(
                    {
                        "source": source,
                        "mean_brightness": float(panel.mean()),
                        "media_sequence": parsed["segments"][-1]["sequence"],
                    }
                )
            image = Path(temporary) / "two-actual-video-frames.jpg"
            cv2.imwrite(str(image), np.vstack(panels))
            print(
                json.dumps(
                    {
                        "frame_file": str(image),
                        "source_frames": [0, 50],
                        "sources": summaries,
                        "temporary_only": True,
                    }
                ),
                flush=True,
            )
            remaining = min(25, 50 - (time.monotonic() - start))
            if remaining > 0:
                time.sleep(remaining)
    print("Deleted all temporary visual-audit media", flush=True)


if __name__ == "__main__":
    main()
