"""Export actual FHWA survey linework and explicit scene provenance for the 3D view."""

import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import cv2
import numpy as np
import shapefile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/reality-v6"


def main():
    source = DATA / "support/gis-files/LA-UniversalCity.shp"
    reader = shapefile.Reader(str(source))
    lines = []
    for record in reader.iterShapeRecords():
        layer = record.record["LAYER"]
        if layer not in {"100", "120", "150", "154", "300"}:
            continue
        points = (np.asarray(record.shape.points)[:, :2] - [6452300, 1873700]) * 1200 / 3937
        valid = (
            (points[:, 0] > -110)
            & (points[:, 0] < 140)
            & (points[:, 1] > -90)
            & (points[:, 1] < 190)
        )
        boundaries = list(record.shape.parts) + [len(points)]
        for begin, end in zip(boundaries[:-1], boundaries[1:], strict=True):
            run = []
            for point, keep in zip(points[begin:end], valid[begin:end], strict=True):
                if keep:
                    run.append(np.round(point, 3).tolist())
                else:
                    if len(run) > 1:
                        lines.append({"layer": layer, "points": run})
                    run = []
            if len(run) > 1:
                lines.append({"layer": layer, "points": run})
    calibration = json.loads((DATA / "camera4-calibration.json").read_text())
    output = {
        "location": "Lankershim Boulevard / Main Street, Los Angeles",
        "raw_to_world": calibration["raw_to_world"],
        "calibration_hull_world_m": cv2.convexHull(
            np.float32([point["world_center_m"] for point in calibration["points"]])
        )
        .reshape(-1, 2)
        .astype(float)
        .tolist(),
        "calibration_check_rmse_m": calibration["validation_rmse_m"],
        "survey_lines": lines,
        "survey_legend": {
            "100": "curbed road edge",
            "120": "sidewalk",
            "150": "edge of travelled way",
            "154": "lane striping",
            "300": "building outline",
        },
        "survey_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "provenance": {
            "surveyed": "FHWA supplied GIS linework, NAD83 CA zone 5 US survey feet, locally translated and converted to metres",
            "estimated": "SUMO lane geometry, approximate signal heads, vehicle dimensions, homography-derived roof-center positions",
            "decorative": "Building heights/facades, vegetation, surface materials and lighting are illustrative; not surveyed or weather measurements",
            "signal": "RSM-derived approximate phases; actual lamp agreement is not validated",
            "uncertainty": "0.758 m is a three-point same-frame calibration check, not whole-camera accuracy. Roof parallax and extrapolation remain unquantified. No smoothing changes the measured benchmark outputs.",
        },
    }
    with zipfile.ZipFile(ROOT / "artifacts/reality/v6/native-sumo-run.zip") as archive:
        routes = ET.fromstring(archive.read("routes.xml"))
        types = {kind.get("id"): float(kind.get("length")) for kind in routes.findall("vType")}
        output["native_vehicle_lengths_m"] = {
            vehicle.get("id"): types[vehicle.get("type")] for vehicle in routes.findall("vehicle")
        }
    destination = ROOT / "artifacts/reality/v7/scene.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        previous = json.loads(destination.read_text())
        if "orthophoto" in previous:
            output["orthophoto"] = previous["orthophoto"]
    destination.write_bytes(json.dumps(output, separators=(",", ":")).encode())
    print(
        json.dumps(
            {
                "survey_lines": len(lines),
                "bytes": destination.stat().st_size,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
