"""Window-read a true georeferenced FHWA image; never synthesize street imagery."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "data/reality-v7/ortho/LA-UniversalCity.tif"
    scale = 1200 / 3937
    xmin, ymin, xmax, ymax = -110, -90, 140, 190
    with rasterio.Env(GDAL_CACHEMAX=16_000_000), rasterio.open(source) as dataset:
        bounds = (
            6452300 + xmin / scale,
            1873700 + ymin / scale,
            6452300 + xmax / scale,
            1873700 + ymax / scale,
        )
        window = from_bounds(*bounds, transform=dataset.transform)
        image = dataset.read(window=window, out_shape=(3, 1837, 1641))
    out = ROOT / "artifacts/reality/v7"
    path = out / "historical-ortho.webp"
    white = np.all(image >= 250, axis=0).astype(np.uint8)
    _, labels = cv2.connectedComponents(white)
    border = set(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]).tolist()) - {
        0
    }
    alpha = np.where(np.isin(labels, list(border)), 0, 255).astype(np.uint8)
    color = np.moveaxis(image, 0, 2)[:, :, ::-1]
    cv2.imwrite(str(path), np.dstack([color, alpha]), [cv2.IMWRITE_WEBP_QUALITY, 88])
    scene_path = out / "scene.json"
    scene = json.loads(scene_path.read_text())
    scene["orthophoto"] = {
        "file": path.name,
        "bounds_m": [xmin, ymin, xmax, ymax],
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": "FHWA NGSIM Lankershim aerial ortho, 2005, CC BY-SA 3.0 supporting dataset",
        "source_sha256": "bd6f078ad9f3a979df2633bfad7783347cde588575e0ab777474bd93af347c92",
        "scope": "Static historical ground context. Cropped/reprojected by the supplied world file, web encoded; connected white border nodata made transparent. Parked/moving vehicles baked into the photo are not synchronized tracks. Surface texture is not a geometry or physical validation claim.",
    }
    scene_path.write_bytes(json.dumps(scene, separators=(",", ":")).encode())
    print(json.dumps(scene["orthophoto"]), flush=True)


if __name__ == "__main__":
    main()
