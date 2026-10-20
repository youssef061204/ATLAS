"""Package actual complete ATLAS 7 video trajectories and free-running native SUMO.

Historical source media is reused byte-for-byte from the verified v6 web transcode.
Raw detector observations and offline gap estimates remain distinguishable.
"""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/reality/v7"
FRAMES = ROOT / "data/reality-v7/full-v7-lankershim-continuity-v2-interpolated"
NATIVE = (
    ROOT
    / "data/reality-v7/birth-reconstruction-full-v7-lankershim-continuity-v2-interpolated-600-1000-complete-v7"
)


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def compact_gzip(path, value):
    path.write_bytes(gzip.compress(json.dumps(value, separators=(",", ":")).encode(), mtime=0))


def main():
    native_directory = ROOT / "data/reality-v7/eager-insertion/duration-1122"
    manifest = json.loads(
        (ROOT / "artifacts/reality/v6/manifest.json").read_text(encoding="utf-8-sig")
    )
    raw = json.loads((ROOT / "data/reality-v7/production-lankershim/run.json").read_text())
    run = json.loads((FRAMES / "run.json").read_text())
    if (
        sha(FRAMES / "frames.jsonl.gz") != run["frames_sha256"]
        or raw["performance"]["processed_frames"] != 11220
    ):
        raise ValueError("Complete perception output changed")
    metrics = json.loads((native_directory / "validation.json").read_text())
    if metrics["simulation_duration_s"] != 1122:
        raise ValueError("Incomplete native reconstruction")
    native = {}
    with gzip.open(native_directory / "simulation.fcd.xml.gz", "rb") as handle:
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
    if sorted(native) != list(range(1122)):
        raise ValueError("Missing complete native output times")
    first_native = {}
    for sampled_time, rows in sorted(native.items()):
        for row in rows:
            first_native.setdefault(row[0], sampled_time)
    tracks = defaultdict(
        lambda: {
            "first_frame": None,
            "last_frame": None,
            "actual_observations": 0,
            "inferred_observations": 0,
            "missing_intervals_s": [],
            "source_ids": set(),
            "class": "car",
            "last_actual": None,
        }
    )
    chunks, batch, total = [], [], 0
    with gzip.open(FRAMES / "frames.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            frame = json.loads(line)
            if frame["index"] != total:
                raise ValueError("Missing or duplicate video processing frame")
            rows = []
            for obj in frame["objects"]:
                identity = obj["id"]
                inferred = bool(obj.get("inferred"))
                rows.append(
                    [
                        identity,
                        *obj["bbox"],
                        obj["class"],
                        obj["confidence"],
                        inferred,
                        obj.get("source_track_id"),
                    ]
                )
                track = tracks[identity]
                track["class"] = obj["class"]
                track["first_frame"] = (
                    total if track["first_frame"] is None else track["first_frame"]
                )
                track["last_frame"] = total
                track["inferred_observations" if inferred else "actual_observations"] += 1
                if obj.get("source_track_id") is not None:
                    track["source_ids"].add(obj["source_track_id"])
                if not inferred:
                    prior = track["last_actual"]
                    if prior is not None and total - prior > 1:
                        track["missing_intervals_s"].append([(prior + 1) / 10, total / 10])
                    track["last_actual"] = total
            batch.append(rows)
            total += 1
            if len(batch) == 600 or total == 11220:
                first = total - len(batch)
                start_s, end_s = first // 10, total // 10
                name = f"replay-{start_s:04d}.json.gz"
                compact_gzip(
                    OUT / name,
                    {
                        "start_frame": first,
                        "frames": batch,
                        "simulation": {
                            str(t): native.get(t, []) for t in range(start_s, min(end_s + 1, 1122))
                        },
                    },
                )
                chunks.append(
                    {"start_s": start_s, "file": name.removesuffix(".gz"), "frames": len(batch)}
                )
                batch = []
    if total != 11220:
        raise ValueError("Incomplete presentation frame count")
    index = {}
    admitted = {
        v.get("id"): v for v in ET.parse(native_directory / "routes.xml").findall("vehicle")
    }
    lengths = {
        v.get("id"): float(v.get("length"))
        for v in ET.parse(native_directory / "routes.xml").findall("vType")
    }
    for identity, track in tracks.items():
        vehicle = admitted.get(f"cv_{identity}")
        index[f"cv_{identity}"] = {
            k: (sorted(v) if isinstance(v, set) else v)
            for k, v in track.items()
            if k != "last_actual"
        }
        index[f"cv_{identity}"].update(
            {
                "requested_admission_s": float(vehicle.get("depart"))
                if vehicle is not None
                else None,
                "simulated_admission_s": first_native.get(f"cv_{identity}"),
                "native_start_scope": "First sampled native FCD state, 1 Hz; requested depart time is not actual admission",
                "native_length_m": lengths[vehicle.get("type")] if vehicle is not None else None,
            }
        )
    compact_gzip(OUT / "tracks.json.gz", index)
    cv = json.loads((OUT / "evaluation-full-v7-lankershim-600-1000-window.json").read_text())
    secondary = json.loads(
        (
            OUT / "evaluation-full-v7-lankershim-continuity-v2-interpolated-600-1000-window.json"
        ).read_text()
    )
    (OUT / "cv-validation.json").write_bytes(json.dumps(cv, indent=2).encode())
    (OUT / "cv-driven-validation.json").write_bytes(json.dumps(metrics, indent=2).encode())
    with zipfile.ZipFile(OUT / "native-sumo-evidence.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in [
            "network.net.xml",
            "routes.xml",
            "inputs.json",
            "simulation.fcd.xml.gz",
            "tripinfo.xml",
            "sumo.log",
            "validation.json",
        ]:
            archive.writestr(name, (native_directory / name).read_bytes())
    scene = json.loads((OUT / "scene.json").read_text())
    scene["native_vehicle_lengths_m"] = {
        key: value["native_length_m"]
        for key, value in index.items()
        if value["native_length_m"] is not None
    }
    (OUT / "scene.json").write_bytes(json.dumps(scene, separators=(",", ":")).encode())
    summary = {k: v for k, v in metrics.items() if k != "series"}
    manifest.update(
        {
            "schema": "atlas-real-video-replay-7.0",
            "title": "Reality Engine / Lankershim",
            "status": "Verified real-video perception gains; approximate physical reconstruction remains unaccepted",
            "processing": "Precomputed actual multiscale YOLOv8n-VisDrone / ByteTrack, explicit offline short-gap estimates; native free-running SUMO",
            "video": "../v6/lankershim-camera4.mp4",
            "poster": "../v6/poster.jpg",
            "chunks": chunks,
            "performance": raw["performance"],
            "metrics": summary,
            "cv": {
                "identity": cv["identity"],
                "spatial_matching": {"reference_coverage": cv["reference_coverage"]},
                "speed_mps_matched_pairs": cv["matched_speed_mps"],
            },
            "secondary_offline_cv": {
                k: v for k, v in secondary.items() if k not in ["per_frame", "runtime"]
            },
            "input_result_sha256": raw["result_sha256"],
            "native_fcd_sha256": sha(native_directory / "simulation.fcd.xml.gz"),
            "exporter_sha256": sha(Path(__file__)),
            "conditioning": metrics["conditioning"],
            "research": {k: "../v6/" + v for k, v in manifest["research"].items()},
            "files": {},
        }
    )
    # Do not retain provenance fields that describe the old run as current.
    for key in [
        "measured_runtime_sha256",
        "measured_runtime_archive",
        "native_builder_sha256",
        "protocol_sha256",
    ]:
        manifest.pop(key, None)
    manifest["perception_freeze_sha256"] = sha(ROOT / "docs/perception-v7-frozen.json")
    manifest["native_builder_sha256"] = sha(ROOT / "scripts/evaluate_insertion_v7.py")
    license_text = (ROOT / "artifacts/reality/v6/source-license.txt").read_text()
    (OUT / "source-license.txt").write_bytes(
        (
            license_text
            + "\nATLAS 7: Separate model-derived boxes, marked offline gap estimates, birth-initialized native SUMO reconstruction and 3D display. FHWA historical orthophoto and GIS context from the NGSIM support package: CC BY-SA 3.0, https://creativecommons.org/licenses/by-sa/3.0/ . Orthophoto cropped/georeferenced/transcoded with connected source-border nodata made transparent. Static photographed vehicles are not dynamic observations. Illustrative building heights/facades, trees and original procedural vehicle meshes are not measured geometry.\n"
        ).encode()
    )
    (OUT / "description.vtt").write_bytes(
        (ROOT / "artifacts/reality/v6/description.vtt").read_bytes()
    )
    names = [c["file"] + ".gz" for c in chunks] + [
        "tracks.json.gz",
        "cv-validation.json",
        "cv-driven-validation.json",
        "native-sumo-evidence.zip",
        "source-license.txt",
        "description.vtt",
        "scene.json",
        scene["orthophoto"]["file"],
    ]
    for name in names:
        path = OUT / name
        manifest["files"][name] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    (OUT / "manifest.json").write_bytes(json.dumps(manifest, indent=2).encode())
    print(
        json.dumps(
            {
                "actual_processed_frames": total,
                "chunks": len(chunks),
                "track_ids_not_unique_vehicles": len(tracks),
                "native_admissions": len(admitted),
                "offline_inferred_boxes": sum(t["inferred_observations"] for t in tracks.values()),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
