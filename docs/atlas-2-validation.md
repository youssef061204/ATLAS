# Incremental verification and known boundaries

Current v3 continuation: **107 Python tests pass**; see [generated exact metrics](VERIFIED_ENGINEERING_METRICS.md), [new results](atlas-3-results.md) and [v3 acceptance ledger](atlas-3-status.md). The counts and checks below describe earlier increments and are retained as historical verification, not the latest final run. The complete frozen nominal/transfer study now contains 560 actual paired-policy simulations. Eighteen actual official snapshots across five cities are retained as aggregate evidence; three near-corridor observation-conditioned pairs complete, while four zero-motor snapshots correctly refuse demand conversion.

Baseline: 55 Python tests; existing frontend lint/types/format pass; 8 native browser tests pass. A fresh untouched Linux selected-controller replay matches published seed 5001 exactly (21.177817772778404 s). Original benchmark JSONs/source hashes remain unchanged.

New suite initially reaches 84 Python tests, including all original tests, ten randomized safety cases covering 30,000 steps, actual saved official-source provenance, HTTP budget/redirect/access failure checks, signed request replay rejection, independent calibration, temporal interval leakage and API authorization/exports. Additional integration outcomes must be recorded from actual runs, not inferred from mocked success.

Three new production-build browser tests verify five city catalogs and map toggles, exact saved trace scrubbing/playback, economic export and 390-pixel layouts with no page errors. Public replay regressions require `ATLAS_PUBLIC_TEST=true`; otherwise the historical public tests intentionally skip. Lint, types, formatting and native/public builds are separate checks.

Actual backend job smoke: authenticated `POST /api/operations/experiments` queued and completed a Toronto SUMO run, seed 19001, 120 seconds, 18.3 s mean delay and zero modeled lamp-state violations. Unauthorized submission returned 401. Docker API startup with restored pinned city inputs succeeded on a separate loopback port, preserving the existing application containers.

The final evidence report will include complete five-city nominal and RESCO cohorts, hashes, all failures, mean/SD/CIs, paired differences and performance regressions. Single-seed resilience/ablation results remain development sensitivity checks. No city is calibrated from two snapshots. Official metadata/image samples establish current access only; sparse sources do not provide continuous trajectories.

Local dependency audit found no known vulnerabilities in the pinned Python requirements or frontend npm dependency tree at this check. Newly added pyproj must be included in the final lock/audit verification. Hosted CI has been updated but is not claimed executed until a real remote run is observed.

Known limitations: uncalibrated demand and generated signals; uncertain camera capture times; no independently measured five-city CV accuracy; pressure fallback can regress; outage fallback can worsen delay; empirical forecast intervals under-cover; search is slower in the declared synthetic microbenchmark; unsupported emergency/transit execution; no commercial controller comparison, hardware certification, municipal field study or completed ATLAS 2.0 production deployment.
