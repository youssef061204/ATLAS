"""Native single-process forecast-service latency; not HTTP or accuracy evaluation."""

import json
import platform
from pathlib import Path

import numpy as np
from atlas.city_network import sha
from atlas.forecast_v3 import predict_evaluated


def main():
    source = "backend/atlas/forecast_v3.py"
    report = Path("artifacts/cities/forecast-v3.json")
    evidence = json.loads(report.read_text(encoding="utf-8"))
    evidence["runtime_source_sha256"] = sha(source)
    report.write_text(json.dumps(evidence, allow_nan=False), encoding="utf-8")
    x = np.full((207, 6), 50.0)
    cold = predict_evaluated(x.copy(), "2012-06-04T12:00", 5)["end_to_end_inference_ms"]
    timings = [
        predict_evaluated(x.copy(), "2012-06-04T12:00", 5)["end_to_end_inference_ms"]
        for _ in range(100)
    ]
    result = {
        "cold_ms": cold,
        "warm_ms_p50": float(np.percentile(timings, 50)),
        "warm_ms_p95": float(np.percentile(timings, 95)),
        "samples": len(timings),
        "runtime_source_sha256": sha(source),
        "profile_source_sha256": sha(__file__),
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_threads": 4,
        },
        "scope": "Native Python service: checksums, context, causal features, cached checkpoint, 207 predictions. Excludes HTTP/frontend. Constant-input latency probe, not accuracy experiment or repeated isolated runs.",
    }
    Path("artifacts/cities/forecast-runtime-profile.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
