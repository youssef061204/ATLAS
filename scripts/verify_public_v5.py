"""Verify ordinary unauthenticated production responses against published evidence."""

import gzip
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx


def main():
    atlas = os.getenv("ATLAS_LIVE_URL", "https://atlas-mu-murex.vercel.app")
    portfolio = os.getenv("PORTFOLIO_URL", "https://youssefelsokkary.vercel.app")
    evidence = Path("artifacts/cities/v5")
    media_root = Path("artifacts/portfolio/v5")
    checks = []
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for file in (
            "calibration-readiness.json",
            "forecast-results.json",
            "geometry-investigation.json",
            *(
                f"studio-{city}-{case}.json"
                for city in ("toronto", "london", "seattle", "austin", "calgary")
                for case in ("low", "nominal", "high", "incident", "outage", "shift")
            ),
            *(
                f"pilot-{case}.json"
                for case in ("low", "nominal", "high", "incident", "outage", "shift")
            ),
        ):
            path = f"/demo/cities/v5/{file}"
            response = client.get(atlas + path)
            response.raise_for_status()
            expected = hashlib.sha256((evidence / file).read_bytes()).hexdigest()
            assert hashlib.sha256(response.content).hexdigest() == expected, path
            checks.append({"url": atlas + path, "status": response.status_code, "sha256": expected})
        series = json.loads(
            gzip.decompress((evidence / "count-demand-series.json.gz").read_bytes())
        )
        for city, rows in series["cities"].items():
            response = client.get(f"{atlas}/demo/cities/v5/demand-{city}.json")
            response.raise_for_status()
            assert response.json() == rows, city
            checks.append(
                {"url": str(response.url), "status": response.status_code, "rows": len(rows)}
            )
        for file in (
            *[
                f"{name}.jpg"
                for name in (
                    "command-center",
                    "real-cv",
                    "calibration",
                    "robust-control",
                    "benchmarks",
                )
            ],
            "walkthrough.mp4",
        ):
            stem, suffix = file.rsplit(".", 1)
            response = client.get(f"{portfolio}/projects/atlas/{stem}-v5.{suffix}")
            response.raise_for_status()
            expected = hashlib.sha256((media_root / file).read_bytes()).hexdigest()
            assert hashlib.sha256(response.content).hexdigest() == expected, file
            checks.append(
                {"url": str(response.url), "status": response.status_code, "sha256": expected}
            )
        for path in (
            "/api/execution/jobs",
            "/api/operations/control-v4/jobs",
            "/api/operations/intelligence",
        ):
            response = client.post(atlas + path, json={"city": "toronto", "seed": 56001})
            assert response.status_code == 409, path
            checks.append(
                {
                    "url": atlas + path,
                    "status": response.status_code,
                    "mutation": "rejected in public demo",
                }
            )
    record = {
        "schema_version": "atlas-production-integrity-5.0",
        "verified_at": datetime.now(UTC).isoformat(),
        "atlas_url": atlas,
        "portfolio_url": portfolio,
        "checks": checks,
        "scope": "Ordinary unauthenticated HTTPS requests; real published evidence/media integrity and disabled public mutations. Browser/CI checks and deployment metadata recorded separately.",
    }
    (evidence / "verification-production.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    print(f"Verified {len(checks)} unauthenticated production evidence/media/mutation checks")


if __name__ == "__main__":
    main()
