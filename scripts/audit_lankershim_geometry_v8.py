"""Audit current SUMO lane placement against FHWA video, GIS and 0-300 s reference.

The official GIS layer is unclassified survey/CAD linework. This overlay does
not claim it is a certified lane-center survey. The NGSIM trajectory sample is
development data and cannot serve as an independent validation holdout.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import shapefile
from calibrate_physics_v7 import reference_states
from diagnose_ngsim_v7 import development_observations
from reconstruct_births_v7 import lane_project
from reconstruct_ngsim_v6 import METRES, ORIGIN, road_model

ROOT = Path(__file__).resolve().parents[1]
SOURCE_VIDEO = ROOT / "data/reality-v6/lankershim-camera4-0830am-0845am.avi"
CALIBRATION = ROOT / "data/reality-v6/camera4-calibration.json"
GIS = ROOT / "data/reality-v6/support/gis-files/LA-UniversalCity"
SIGNALS = ROOT / "data/reality-v6/support/gis-files/signals-and-ramp-meters"
NETWORK = ROOT / "data/reality-v7/eager-insertion/duration-300/network.net.xml"
ARTIFACT = ROOT / "artifacts/reality/v8/geometry-development-audit.json"
OVERLAY = ROOT / "artifacts/reality/v8/geometry-video-overlay.png"
FRAME = 600


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def finite_percentile(values: list[float], percentile: float) -> float | None:
    return float(np.percentile(values, percentile)) if values else None


def lanes(network: ET.Element) -> dict[str, list[dict]]:
    result = defaultdict(list)
    for edge in network.findall("edge"):
        if edge.get("id") not in {"N_in", "N_out"}:
            continue
        for lane in edge.findall("lane"):
            shape = np.array(
                [[float(value) for value in pair.split(",")] for pair in lane.get("shape").split()]
            )
            result[edge.get("id")].append(
                {
                    "id": lane.get("id"),
                    "index": int(lane.get("index")),
                    "length_m": float(lane.get("length")),
                    "width_m": float(lane.get("width", "3.35")),
                    "shape": shape,
                }
            )
    return result


def world_to_raw(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    raw = cv2.perspectiveTransform(
        np.asarray(points, dtype=np.float32).reshape(-1, 1, 2),
        np.linalg.inv(homography),
    )
    return raw.reshape(-1, 2)


def make_overlay(
    reference: list[dict],
    network_lanes: dict[str, list[dict]],
    signal_marker_world: np.ndarray,
    junction_world: np.ndarray,
    calibration: dict,
) -> dict:
    cap = cv2.VideoCapture(str(SOURCE_VIDEO))
    cap.set(cv2.CAP_PROP_POS_FRAMES, FRAME)
    success, image = cap.read()
    cap.release()
    if not success:
        raise RuntimeError("Could not decode exact source frame 600")
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    H = np.array(calibration["raw_to_world"], dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=160)
    for axis in axes:
        axis.imshow(image)
        axis.set_xlim(0, image.shape[1])
        axis.set_ylim(image.shape[0], 0)
        axis.axis("off")
    axes[0].set_title("Original FHWA camera 4 · frame 601")
    axes[1].set_title("Source-aligned audit · development calibration")
    official = shapefile.Reader(str(GIS))
    line_count = 0
    for record, shape in zip(official.records(), official.shapes(), strict=True):
        if record.LAYER != "154" or len(shape.points) < 2:
            continue
        world = (np.array(shape.points, dtype=float) - ORIGIN) * METRES
        if not (
            world[:, 0].max() > -35
            and world[:, 0].min() < 80
            and world[:, 1].max() > -30
            and world[:, 1].min() < 180
        ):
            continue
        pixels = world_to_raw(world, H)
        if pixels[:, 0].max() < -10 or pixels[:, 0].min() > 650:
            continue
        if pixels[:, 1].max() < -10 or pixels[:, 1].min() > 490:
            continue
        axes[1].plot(pixels[:, 0], pixels[:, 1], color="#facc15", lw=0.65, alpha=0.38)
        line_count += 1
    lane_count = 0
    for edge_lanes in network_lanes.values():
        for lane in edge_lanes:
            pixels = world_to_raw(lane["shape"], H)
            axes[1].plot(pixels[:, 0], pixels[:, 1], color="#d946ef", lw=1.2, alpha=0.9)
            lane_count += 1
    if reference:
        pixels = world_to_raw(np.array([row["point"] for row in reference]), H)
        visible = (
            (pixels[:, 0] >= 0)
            & (pixels[:, 0] < image.shape[1])
            & (pixels[:, 1] >= 0)
            & (pixels[:, 1] < image.shape[0])
        )
        axes[1].scatter(
            pixels[visible, 0],
            pixels[visible, 1],
            s=14,
            c="#4ade80",
            edgecolors="black",
            linewidths=0.35,
        )
    marker = world_to_raw(signal_marker_world[None, :], H)[0]
    junction = world_to_raw(junction_world[None, :], H)[0]
    axes[1].scatter([marker[0]], [marker[1]], marker="D", s=48, c="#facc15", edgecolors="black")
    axes[1].scatter([junction[0]], [junction[1]], marker="x", s=65, c="#f87171", linewidths=2)
    fig.text(
        0.5,
        0.02,
        "Yellow: unclassified official GIS linework  ·  Magenta: SUMO lane centers  ·  "
        "Green: FHWA reference body centers  ·  Diamond: official signal marker  ·  X: modeled junction",
        ha="center",
        fontsize=8,
    )
    fig.subplots_adjust(top=0.90, bottom=0.11, left=0.02, right=0.98, wspace=0.06)
    OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OVERLAY, dpi=160)
    plt.close(fig)
    return {
        "source_frame_index_zero_based": FRAME,
        "source_video_fps": 10,
        "official_gis_layer_154_polylines_drawn": line_count,
        "sumo_lane_centerlines_drawn": lane_count,
        "reference_centers_visible": int(visible.sum()) if reference else 0,
        "scope": "Development-calibrated homography; FHWA GIS layer 154 is unclassified linework, not verified lane-center truth",
    }


def main() -> None:
    source = development_observations(301)
    source = source[source.t < 300]
    road, _ = road_model(source)
    all_states, _ = reference_states(source, road)
    reference_points = {
        (t, row["id"]): row["point"] for t, rows in all_states.items() for row in rows
    }
    network = ET.parse(NETWORK).getroot()
    network_lanes = lanes(network)
    official_signals = shapefile.Reader(str(SIGNALS))
    matches = [
        np.asarray(shape.points[0], dtype=float)
        for record, shape in zip(official_signals.records(), official_signals.shapes(), strict=True)
        if record.Signal_No == 89
    ]
    if len(matches) != 1:
        raise ValueError("Expected one official GIS signal marker 89")
    marker_world = (matches[0] - ORIGIN) * METRES
    modeled_junction = network.find("junction[@id='J']")
    if modeled_junction is None:
        raise ValueError("Expected current J junction")
    junction_world = np.array([float(modeled_junction.get("x")), float(modeled_junction.get("y"))])
    per_lane = defaultdict(list)
    nearest_index = defaultdict(Counter)
    for row in source.itertuples():
        tick = round(row.t * 10)
        if tick % 10 or not 1090 <= row.local_y <= 1360:
            continue
        if row.section_id != 4 or row.direction not in (2, 4) or not 1 <= row.lane_id <= 4:
            continue
        point = reference_points.get((tick, str(row.vehicle_id)))
        if point is None:
            continue
        edge = "N_in" if row.direction == 4 else "N_out"
        candidates = [
            (lane_project(np.array(point), lane["shape"])[0], lane["index"])
            for lane in network_lanes[edge]
        ]
        distance, index = min(candidates)
        key = f"direction_{row.direction}_reference_lane_{row.lane_id}"
        per_lane[key].append(float(distance))
        nearest_index[key][str(index)] += 1
    lane_report = {
        key: {
            "reference_1hz_states": len(values),
            "nearest_sumo_lane_center_median_m": finite_percentile(values, 50),
            "nearest_sumo_lane_center_p90_m": finite_percentile(values, 90),
            "fraction_within_1_675m_lane_half_width": sum(value <= 1.675 for value in values)
            / len(values),
            "fraction_within_4m": sum(value <= 4 for value in values) / len(values),
            "nearest_sumo_lane_index_counts": dict(nearest_index[key]),
        }
        for key, values in sorted(per_lane.items())
    }
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    overlay = make_overlay(
        all_states[FRAME], network_lanes, marker_world, junction_world, calibration
    )
    report = {
        "schema": "atlas-v8-lankershim-geometry-development-audit-1",
        "source_scope": "Previously exposed 0-300 s development only; no independent test scoring",
        "source_sha256": sha(Path(__file__)),
        "official_signal_shp_sha256": sha(SIGNALS.with_suffix(".shp")),
        "official_linework_shp_sha256": sha(GIS.with_suffix(".shp")),
        "baseline_network_sha256": sha(NETWORK),
        "camera_calibration_sha256": sha(CALIBRATION),
        "source_video_sha256": sha(SOURCE_VIDEO),
        "signal_89": {
            "official_marker_world_m": marker_world.tolist(),
            "current_sumo_junction_world_m": junction_world.tolist(),
            "marker_to_junction_distance_m": float(np.linalg.norm(marker_world - junction_world)),
            "scope": "GIS point marks the signal/intersection, not a surveyed stop line or lane center",
        },
        "current_network": {
            "external_edges": [
                edge.get("id")
                for edge in network.findall("edge")
                if not edge.get("id", "").startswith(":")
            ],
            "lane_widths_m": sorted(
                {lane["width_m"] for group in network_lanes.values() for lane in group}
            ),
            "lane_counts_n_in_out": {key: len(value) for key, value in network_lanes.items()},
            "turn_bays_modeled": False,
            "same_main_phase_serves_through_and_turning_connections": True,
            "estimated_geometry": True,
        },
        "nearest_centerline_development": lane_report,
        "nearest_centerline_scope": "This is geometric proximity of annotated body centers to any current direction-compatible SUMO lane; it cannot verify intended lane identity or route legality.",
        "overlay": {**overlay, "file": str(OVERLAY.relative_to(ROOT)), "sha256": sha(OVERLAY)},
        "source_limitations": [
            "The CAD/GIS linework layer has no reliable lane-center semantic labels in the supplied shapefile.",
            "The FHWA timing sheet documents turning movements, but not surveyed turn-bay polyline coordinates.",
            "Camera road-plane homography and reference body centers have calibration and annotation uncertainty.",
            "A nearby signal marker does not validate stop lines, connectivity, signal phase mapping or lane widths.",
        ],
        "physical_geometry_verified": False,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "signal_marker_offset_m": report["signal_89"]["marker_to_junction_distance_m"],
                "lane_groups": len(lane_report),
                "overlay": report["overlay"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
