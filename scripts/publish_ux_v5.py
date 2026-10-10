"""Preserve actual browser laboratory measurements and the measured frontend."""

import hashlib
import json
import zipfile
from pathlib import Path


def main():
    evidence = Path("artifacts/cities/v5")
    after = json.loads((evidence / "ux-performance.json").read_bytes())
    before = json.loads((evidence / "ux-before.json").read_bytes())
    media = json.loads(Path("artifacts/portfolio/v5/provenance.json").read_bytes())
    sources = dict(after["measured_source_sha256"])
    sources.update(
        {f"frontend/{p}": digest for p, digest in media["measured_source_sha256"].items()}
    )
    with zipfile.ZipFile(evidence / "ux-measured-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file, digest in sources.items():
            raw = Path(file).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == digest, file
            archive.writestr(file, raw)
    lighthouse = []
    for stage, name in (
        ("before", "lighthouse-v5-calibration.json"),
        ("after", "lighthouse-v5-calibration-after.json"),
    ):
        raw = Path("data", name).read_bytes()
        result = json.loads(raw)
        lighthouse.append(
            {
                "stage": stage,
                "fetch_time": result["fetchTime"],
                "requested_url": result["requestedUrl"],
                "version": result["lighthouseVersion"],
                "environment": result["environment"],
                "config": result["configSettings"],
                "raw_report_sha256": hashlib.sha256(raw).hexdigest(),
                "scores": {k: v["score"] for k, v in result["categories"].items()},
                "audits": {
                    name: result["audits"][name]
                    for name in (
                        "largest-contentful-paint",
                        "cumulative-layout-shift",
                        "total-blocking-time",
                        "errors-in-console",
                    )
                },
                "measured_source_archive": f"ux-{'before' if stage == 'before' else 'measured'}-source.zip",
            }
        )
    comparison = {
        "schema_version": "atlas-ux-laboratory-comparison-5.0",
        "before": {
            "scans": len(before["scans"]),
            "maximum_cls": max(s["cls"] for s in before["scans"]),
        },
        "after": {
            "scans": len(after["scans"]),
            "maximum_cls": max(s["cls"] for s in after["scans"]),
            "violations": sum(len(s["violations"]) for s in after["scans"]),
        },
        "lighthouse": lighthouse,
        "interventions": [
            "OFL-licensed fonts bundled locally through next/font/local with adjusted fallback metrics",
            "Calibration and control loading panels reserve space before asynchronous evidence arrives",
            "Application icon supplied through the Next.js metadata route",
        ],
        "limitations": [
            "One local sample per city/view/viewport before and after; not a statistically established speedup or field Core Web Vitals",
            "Lighthouse is a separate mobile-throttled laboratory sample, not comparable to unthrottled browser timing",
            "Lighthouse after LCP is higher than before; improved score does not establish universal page-load improvement",
            "Automated accessibility checks are not certification; human participants: 0",
        ],
    }
    (evidence / "ux-comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print("Published actual before/after UX diagnostics and immutable measured frontend source")


if __name__ == "__main__":
    main()
