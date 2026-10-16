"""Package actual historical video/CV/SUMO outputs for synchronized public inspection."""

import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import cv2
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v6"
OUT = ROOT / "artifacts/reality/v6"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run = json.loads((DATA / "production-pipeline/run.json").read_text())
    result_path = Path(run["result_file"])
    result = json.loads(result_path.read_text())
    assert (
        result["performance"]["decoded_frames"]
        == result["performance"]["processed_frames"]
        == 11220
    )
    raw = DATA / "lankershim-camera4-0830am-0845am.avi"
    source = json.loads(raw.with_suffix(".avi.source.json").read_text())
    assert sha(raw) == source["sha256"] and source["zip_crc_verified"]
    assert "by-sa/4.0" in source["license"]["termsLink"]
    video = OUT / "lankershim-camera4.mp4"
    if not video.exists() or video.stat().st_size > 90_000_000:
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-r",
                "10",
                "-i",
                str(raw),
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "30",
                "-preset",
                "slow",
                "-threads",
                "4",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(video),
            ],
            check=True,
            timeout=300,
        )
    capture = cv2.VideoCapture(str(video))
    declared, fps = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), capture.get(cv2.CAP_PROP_FPS)
    count = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if count == 600:
            cv2.imwrite(str(OUT / "poster.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 86])
        count += 1
    capture.release()
    if declared != 11220 or count != declared or abs(fps - 10) > 0.001:
        raise ValueError("Presentation video changed frame count or source cadence")
    simulation = DATA / "cv-driven-reconstruction"
    diagnostics = json.loads((simulation / "validation.json").read_text())
    native = {}
    with gzip.open(simulation / "simulation.fcd.xml.gz", "rb") as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag == "timestep":
                native[round(float(element.get("time")))] = [
                    [
                        v.get("id"),
                        round(float(v.get("x")), 3),
                        round(float(v.get("y")), 3),
                        round(float(v.get("speed")), 2),
                        round(float(v.get("angle")), 2),
                    ]
                    for v in element
                ]
                element.clear()
    network = ET.parse(simulation / "network.net.xml")
    lanes = []
    for edge in network.findall("edge"):
        if edge.get("function") == "internal":
            continue
        for lane in edge:
            if lane.tag == "lane":
                lanes.append(
                    {
                        "id": lane.get("id"),
                        "shape": [
                            [float(x) for x in p.split(",")] for p in lane.get("shape").split()
                        ],
                        "width": float(lane.get("width", 3.35)),
                    }
                )
    junction = network.find("junction[@id='J']")
    junction_shape = [[float(x) for x in p.split(",")] for p in junction.get("shape").split()]
    phases, start = [], 0
    for phase in network.find("tlLogic").findall("phase"):
        end = start + float(phase.get("duration"))
        phases.append({"start": round(start, 2), "end": round(end, 2), "state": phase.get("state")})
        start = end
    signal_heads = []
    lane_lookup = {lane["id"]: lane for lane in lanes}
    seen = set()
    for connection in network.findall("connection"):
        if connection.get("tl") != "J":
            continue
        key = f"{connection.get('from')}_{connection.get('fromLane')}"
        if key not in seen:
            signal_heads.append(
                {
                    "lane": key,
                    "point": lane_lookup[key]["shape"][-1],
                    "index": int(connection.get("linkIndex")),
                }
            )
            seen.add(key)
    chunks = []
    for start_index in range(0, 11220, 600):
        frames = []
        for frame in result["frames"][start_index : start_index + 600]:
            frames.append(
                [
                    [obj["id"], *obj["bbox"], obj["class"], obj["confidence"]]
                    for obj in frame["objects"]
                ]
            )
        start_time, end_time = start_index // 10, min(start_index + 600, 11220) // 10
        payload = {
            "start_frame": start_index,
            "frames": frames,
            "simulation": {
                str(t): native.get(t, []) for t in range(start_time, min(end_time + 1, 1122))
            },
        }
        name = f"replay-{start_time:04d}.json.gz"
        (OUT / name).write_bytes(
            gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0)
        )
        chunks.append(
            {"start_s": start_time, "file": name.removesuffix(".gz"), "frames": len(frames)}
        )
    cv = json.loads((DATA / "cv-validation.json").read_text())
    cv.pop("per_frame", None)
    cv.pop("geometry", None)
    (OUT / "cv-validation.json").write_text(json.dumps(cv, indent=2), encoding="utf-8")
    (OUT / "cv-driven-validation.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    for relative, name in [
        ("raw-video-decode-audit.json", "raw-video-decode-audit.json"),
        ("reconstruction-1.0-15.65-66001/validation.json", "observed-boundary-validation.json"),
    ]:
        (OUT / name).write_bytes((DATA / relative).read_bytes())
    (OUT / "source-license.txt").write_text(
        "Historical video: FHWA NGSIM Lankershim Boulevard, June 16, 2005, Camera 4. Official collection: https://data.transportation.gov/d/uv3e-y54k\nSource and this web transcode: Creative Commons Attribution-ShareAlike 4.0 International, https://creativecommons.org/licenses/by-sa/4.0/ . The transcode changes compression and strips audio; source frame count/cadence are preserved. ATLAS detection overlays are separate, model-generated annotations. This is historical footage, not a live stream.\nIndependent reference observations: FHWA NGSIM, https://data.transportation.gov/d/8ect-6jqj , DOI 10.21949/1504477, catalog CC BY-SA 3.0; only aggregate derived validation metrics are published here, not the raw trajectory table.\nThe legacy metadata PDF also contains older RDE registration/redistribution language. Raw archives, source trajectories and support files remain local/ignored. The video presentation relies on the explicit CC BY-SA 4.0 license of the later official video collection; preserve attribution and license.\n",
        encoding="utf-8",
    )
    (OUT / "description.vtt").write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:18:42.000\nSilent historical traffic video: Lankershim Boulevard, Los Angeles, June 16, 2005. ATLAS boxes and IDs are model predictions; the adjacent SUMO reconstruction is an approximate simulation.\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in diagnostics.items() if key != "series"}
    # Publish only our derived native inputs/output, never the restricted source tables.
    with zipfile.ZipFile(OUT / "native-sumo-run.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in [
            "network.net.xml",
            "routes.xml",
            "inputs.json",
            "simulation.fcd.xml.gz",
            "sumo.log",
        ]:
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 16, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, (simulation / name).read_bytes())
    research_path = OUT / "cityflow-results.json"
    if research_path.exists():
        research = json.loads(research_path.read_text())
        for camera in research["camera_runs"]:
            camera["performance"]["model"] = (
                camera["performance"]["model"].replace("\\", "/").split("/")[-1]
            )
        research["publication_note"] = (
            "Local model paths reduced to basenames; measured values and original source hashes unchanged. Raw source videos/crops/embeddings are not distributed."
        )
        research_path.write_text(json.dumps(research, indent=2), encoding="utf-8")
    manifest = {
        "schema": "atlas-real-video-replay-6.0",
        "title": "Lankershim: video versus reconstruction",
        "status": "Working video-driven baseline experiment; physical fidelity fails, not a validated twin",
        "live": False,
        "processing": "Precomputed actual ATLAS YOLOv8n-VisDrone + ByteTrack; actual native SUMO 1.27.1",
        "video": "lankershim-camera4.mp4",
        "poster": "poster.jpg",
        "width": 640,
        "height": 480,
        "fps": 10,
        "frame_count": count,
        "duration_s": count / fps,
        "chunks": chunks,
        "lanes": lanes,
        "junction": junction_shape,
        "signal_heads": signal_heads,
        "phases": phases,
        "metrics": summary,
        "cv": cv,
        "performance": {
            k: result["performance"][k]
            for k in [
                "processed_frames",
                "decoded_frames",
                "wall_seconds",
                "processed_fps",
                "device",
                "model",
                "tracker",
                "resolution",
            ]
        },
        "timing_scope": "One complete verification run on a shared Windows CPU host; concurrent research/user workloads may affect timing. Not an isolated or cross-workload throughput comparison.",
        "source": {
            "url": source["url"],
            "member": source["member"],
            "source_sha256": source["sha256"],
            "source_crc32": source["crc32"],
            "license": source["license"],
            "attribution": "FHWA NGSIM, Lankershim Boulevard, June 16 2005",
        },
        "input_result_sha256": sha(result_path),
        "native_fcd_sha256": sha(simulation / "simulation.fcd.xml.gz"),
        "exporter_sha256": sha(Path(__file__)),
        "measured_runtime_sha256": "971f11892cc4d7088e9f24a87a29680fb34c663cfe01f207d98eee4e503cf9ee",
        "measured_runtime_archive": "artifacts/cities/v5/cv-runtime-source.zip",
        "decoder_guard_runtime_sha256": sha(ROOT / "backend/atlas/pipeline.py"),
        "native_builder_sha256": sha(ROOT / "scripts/reconstruct_ngsim_v6.py"),
        "model_sha256": "060866322c84caa59d7cbd7874efbe1af5e957a862169f2ac6778a8e7e3c4851",
        "protocol_sha256": sha(ROOT / "docs/ngsim-v6-protocol.json"),
        "research": {
            key: name
            for key, name in {
                "holdout": "holdout-prefix-results.json",
                "cityflow": "cityflow-results.json",
                "live": "live-ingestion-results.json",
            }.items()
            if (OUT / name).exists()
        },
        "files": {},
    }
    for path in sorted(OUT.iterdir()):
        if path.name != "manifest.json" and path.is_file():
            manifest["files"][path.name] = {"sha256": sha(path), "bytes": path.stat().st_size}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        "Packaged",
        count,
        "real frames;",
        len(chunks),
        "synchronized data chunks; video bytes",
        video.stat().st_size,
        flush=True,
    )


if __name__ == "__main__":
    main()
