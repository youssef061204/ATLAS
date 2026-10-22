"""Audit noon camera-5 geospatial inputs without opening afternoon labels.

The official orthophoto establishes metric map coordinates. It does not, by
itself, establish a raw-camera homography or a raw/reference frame offset.
"""

import hashlib
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import shapefile

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "data/reality-v7/peachtree/support"
RAW = ROOT / "data/reality-v7/official-videos/peachtree-camera5-1245pm-0100pm.avi"
OUT = ROOT / "artifacts/reality/v8/peachtree-noon-camera5-registration-readiness.json"
ORTHO_URL = (
    "https://data.transportation.gov/api/views/8ect-6jqj/files/"
    "7244a8b5-077f-4851-bc06-3cfc7a75f0b0?download=true"
)
ORTHO_ZIP = SUPPORT / "peachtree-street-aerial-ortho-photos.zip"
ORTHO_TIF = SUPPORT / "ortho/Atlanta-Peachtree.tif"
ORTHO_TFW = SUPPORT / "ortho/Atlanta-Peachtree.tfw"
GIS = SUPPORT / "gis-files/camera-coverage.shp"
EXPECTED = {
    "orthophoto_zip_sha256": "b981408547d69e9128219e963afe90a052760baab97821b0bad5237fe932ee8f",
    "orthophoto_tif_sha256": "3c21f81cd61fdb6fb7ae1f39cce1921ddd8a6d4c1497a0991eb9d9ec865e907f",
    "orthophoto_tfw_sha256": "c0a669334c0385eb47eb7b51f866ad2ae57b99fa56390bb15e762e33b59832a3",
    "raw_noon_sha256": "972c81eed18d50d1cc6c9cc7e933daf1a6fce9a7bf45df0dd216363d35f32127",
}


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_worldfile(path: Path) -> np.ndarray:
    """Return the affine map from pixel centres to NAD83 survey-foot coordinates."""
    values = [float(line) for line in path.read_text().splitlines()]
    if len(values) != 6:
        raise ValueError("A TIFF worldfile must contain six coefficients")
    a, d, b, e, c, f = values
    transform = np.array([[a, b, c], [d, e, f], [0.0, 0.0, 1.0]])
    if abs(np.linalg.det(transform)) < 1e-10:
        raise ValueError("Singular orthophoto worldfile")
    return transform


def project(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    result = homogeneous @ homography.T
    return result[:, :2] / result[:, 2, None]


def audit() -> dict:
    expected_paths = {
        "orthophoto_zip_sha256": ORTHO_ZIP,
        "orthophoto_tif_sha256": ORTHO_TIF,
        "orthophoto_tfw_sha256": ORTHO_TFW,
        "raw_noon_sha256": RAW,
    }
    for name, path in expected_paths.items():
        if sha256(path) != EXPECTED[name]:
            raise ValueError(f"Official noon source changed: {path}")
    with zipfile.ZipFile(ORTHO_ZIP) as archive:
        if archive.testzip() is not None:
            raise ValueError("Orthophoto ZIP CRC failed")
        members = {
            name: archive.getinfo("aerial-ortho-photos/" + name)
            for name in ("Atlanta-Peachtree.tif", "Atlanta-Peachtree.tfw")
        }
        if any(
            members[name].file_size != (SUPPORT / "ortho" / name).stat().st_size for name in members
        ):
            raise ValueError("Orthophoto extract differs from source member size")

    image = cv2.imread(str(ORTHO_TIF), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("Official orthophoto failed to decode")
    coverage = shapefile.Reader(str(GIS))
    camera5 = next(
        (record.shape for record in coverage.shapeRecords() if int(record.record["Id"]) == 5),
        None,
    )
    if camera5 is None:
        raise ValueError("Official GIS lacks camera-5 coverage")
    xy_ft = np.asarray(camera5.points, dtype=np.float64)
    world = read_worldfile(ORTHO_TFW)
    uv = project(xy_ft, np.linalg.inv(world))
    if not (
        np.isfinite(uv).all()
        and (uv[:, 0] >= 0).all()
        and (uv[:, 1] >= 0).all()
        and (uv[:, 0] < image.shape[1]).all()
        and (uv[:, 1] < image.shape[0]).all()
    ):
        raise ValueError("Camera-5 GIS coverage falls outside official orthophoto")
    roundtrip_ft = float(np.max(np.linalg.norm(project(uv, world) - xy_ft, axis=1)))

    raw = cv2.VideoCapture(str(RAW))
    if not raw.isOpened():
        raise ValueError("Official noon camera-5 video failed to open")
    raw.set(cv2.CAP_PROP_POS_FRAMES, 600)
    ok, frame = raw.read()
    raw.release()
    if not ok:
        raise ValueError("Noon camera-5 frame 600 failed to decode")

    # Exploratory static-feature registration only. With very few inliers and
    # no independent world control points, never publish this as calibration.
    x0 = max(0, int(np.floor(uv[:, 0].min())) - 200)
    y0 = max(0, int(np.floor(uv[:, 1].min())) - 200)
    x1 = min(image.shape[1], int(np.ceil(uv[:, 0].max())) + 200)
    y1 = min(image.shape[0], int(np.ceil(uv[:, 1].max())) + 200)
    tile = image[y0:y1, x0:x1]
    cv2.setRNGSeed(0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    sift = cv2.SIFT_create(nfeatures=20000, contrastThreshold=0.01)
    kp_raw, desc_raw = sift.detectAndCompute(
        clahe.apply(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)), None
    )
    kp_map, desc_map = sift.detectAndCompute(clahe.apply(tile), None)
    pairs = cv2.BFMatcher().knnMatch(desc_raw, desc_map, k=2)
    matches = [first for first, second in pairs if first.distance < 0.72 * second.distance]
    inliers = 0
    if len(matches) >= 4:
        source = np.float32([kp_raw[match.queryIdx].pt for match in matches])
        target = np.float32([kp_map[match.trainIdx].pt for match in matches])
        _, mask = cv2.findHomography(source, target, cv2.RANSAC, 5.0)
        if mask is not None:
            inliers = int(mask.sum())

    return {
        "schema": "atlas-v8-peachtree-noon-camera5-registration-readiness-1",
        "scope": "Noon camera-5 source/geometry audit only; no afternoon reference rows, processed afternoon video, or outcome scores read",
        "official_source": ORTHO_URL,
        "license": "FHWA NGSIM support: CC BY-SA 3.0; raw video: CC BY-SA 4.0",
        "source_sha256": {**EXPECTED, "gis_shp_sha256": sha256(GIS)},
        "orthophoto_members_crc32": {name: f"{info.CRC:08x}" for name, info in members.items()},
        "orthophoto_pixels": [int(image.shape[1]), int(image.shape[0])],
        "worldfile_ft_per_pixel": [float(world[0, 0]), float(world[1, 1])],
        "camera5_coverage_ft": xy_ft.tolist(),
        "camera5_coverage_ortho_pixels": uv.tolist(),
        "gis_orthophoto_roundtrip_max_error_ft": roundtrip_ft,
        "noon_raw_probe_frame": 600,
        "noon_raw_probe_dimensions": [int(frame.shape[1]), int(frame.shape[0])],
        "exploratory_raw_to_ortho_sift": {
            "ratio_test": 0.72,
            "matches": len(matches),
            "ransac_inliers": inliers,
            "independent_ground_controls": 0,
            "accepted_as_registration": False,
            "reason": "Sparse cross-view image features cannot prove a road-plane homography or metric error; independent ground controls and separate validation frames are absent.",
        },
        "raw_reference_frame_offset_verified": False,
        "camera5_metric_registration_verified": False,
        "physical_candidate_frozen": False,
        "afternoon_labels_opened": False,
        "next_gate": "Establish camera-5 raw/reference frame pairs and >=4 road-plane control points with independent noon checks before freezing an image/world transform and any afternoon scorer.",
        "audit_script_sha256": sha256(Path(__file__)),
    }


def main() -> None:
    result = audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "camera5_metric_registration_verified": result[
                    "camera5_metric_registration_verified"
                ],
                "sift_inliers": result["exploratory_raw_to_ortho_sift"]["ransac_inliers"],
                "physical_candidate_frozen": result["physical_candidate_frozen"],
                "artifact": str(OUT),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
