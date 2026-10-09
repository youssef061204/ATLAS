"""Publish concise verification counts from actual local machine reports."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def main():
    reports = {}
    for name in ("pytest", "native-browser", "public-browser"):
        path = Path(f"data/atlas-v3-{name}.xml")
        tree = ET.parse(path).getroot()
        rows = [tree] if tree.tag == "testsuite" else list(tree.findall("testsuite"))
        totals = {
            key: sum(int(row.attrib.get(key, 0)) for row in rows)
            for key in ("tests", "failures", "errors", "skipped")
        }
        totals["passed"] = (
            totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
        )
        if totals["failures"] or totals["errors"]:
            raise ValueError(f"Cannot publish a passing verification claim for {name}")
        reports[name] = {
            **totals,
            "local_report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    python = json.loads(Path("data/atlas-v3-dependency-audit.json").read_text())
    npm_bytes = Path("data/atlas-v3-npm-audit.json").read_bytes()
    npm = json.loads(
        npm_bytes.decode(
            "utf-16" if npm_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        )
    )
    audits = {
        "python_dependencies_checked": len(python["dependencies"]),
        "python_known_vulnerabilities": sum(
            len(item.get("vulns", [])) for item in python["dependencies"]
        ),
        "npm_vulnerabilities": npm["metadata"]["vulnerabilities"],
    }
    output = {
        "verified_at": datetime.now(UTC).isoformat(),
        "scope": "Actual local execution, not hosted CI or production deployment verification. Native/public suites contain intentionally inapplicable cases. Accessibility scans are automated checks, not certification or human usability findings.",
        "reports": reports,
        "audits": audits,
        "other_checks": [
            "Frontend lint/typecheck/format and native/public production builds passed",
            "Ruff lint/format and backend compile/startup passed",
            "Own Docker worker completed actual jobs and preserved completed results across an actual restart",
            "Actual running SUMO cancellation reached cancelled state",
            "Five-area desktop/mobile accessibility scans and actual scene-editor scan returned no violations",
            "Frozen sources/protocols and six lossless evidence archives verified",
            "Portfolio lint/typecheck/build and desktop/mobile media/link smoke checks passed",
        ],
        "limitations": [
            "Shared developer host; no isolated production load SLA",
            "Python TestClient emitted one Starlette deprecation warning",
            "City calibration and natural-weather perception accuracy remain unvalidated",
            "This report does not establish remote deployment or CI status",
        ],
    }
    Path("artifacts/cities/verification-v3.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print({name: report["passed"] for name, report in reports.items()}, audits)


if __name__ == "__main__":
    main()
