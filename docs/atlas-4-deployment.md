# ATLAS 4.0 release and production verification

Verified on 10 October 2026. Both existing GitHub repositories and Vercel projects were reused. Main branches were pushed normally; historical commits and published benchmarks remain intact. No duplicate project, force-push, paid remote worker or automatic model/controller promotion was introduced.

| Production | Application commit | Ready deployment |
|---|---|---|
| [ATLAS](https://atlas-mu-murex.vercel.app) | `2cdeffa9a765a251c1aa79bb3172a1230583aac3` | `dpl_F7mVwXixyKm1Wfyp3ktabg62tD13` |
| [Portfolio](https://youssefelsokkary.vercel.app/projects/atlas) | `d98be9795f73f326b4b9f401b64b1e8bdaa9e966` | `dpl_G4RWtpCWBBQk37PoUx6XSGZ3cR7b` |

Vercel deployment metadata confirms each intended project, production alias, main branch and source commit. Public checks use ordinary unauthenticated browser/HTTP requests to the production domains. Subsequent documentation/evidence commits do not change the deployed frontend or backend source trees.

## Executed verification

- 134 Python tests pass; one existing Starlette/httpx deprecation warning remains.
- All 26 native browser tests pass against the actual loopback Docker worker and production frontend, including real CV processing, observation-conditioned SUMO pairs, cached-MPC execution and pilot export.
- 18 browser tests pass against the actual ATLAS production domain. Three authenticated native-worker tests are intentionally skipped publicly and pass in the separate native suite.
- 38 local production browser accessibility scans cover desktop/mobile routes and expanded historical evidence; no automated violations or horizontal overflow. This is not human usability measurement or a WCAG certification.
- Frontend lint, types, formatting and native/public production builds pass. Backend lint, formatting, compilation and actual Docker CV/SUMO startup/integration pass.
- Original v3 evidence verification passes. The v4 verifier checks 52,679 source bins, 2,150 development/validation/held-out deterministic episodes, 140 cooperative-policy training/evaluation episodes, frozen protocols, raw archive digests, ML/CV/UX source hashes and telemetry qualifications.
- [GitHub release CI](https://github.com/youssef061204/ATLAS/actions/runs/38024811209) succeeds for the deployed application commit, including Linux Python/browser checks, raw evidence verification and an actual SUMO smoke test.
- 22 unauthenticated production data/media/mutation checks pass. Eleven public research responses match committed artifacts exactly, eight portfolio assets match their source bytes, and three native mutation routes reject public writes.
- The patched portfolio passes lint, types and production build. Actual desktop/mobile browsers verify the prominent ATLAS card, 18.94% Seattle metric, controller-cost explanation, optimized images, working video and live/GitHub links. All ATLAS documentation links resolve. LinkedIn blocks the automated checker with status 999; that is not an ATLAS link failure.

[Local verification record](../artifacts/cities/v4/verification-local.json) and [production verification record](../artifacts/cities/v4/verification-production.json) preserve actual counts, deployment metadata, digests, browser outcomes and scope.

## Security and hosting scope

The ATLAS frontend audit reports no known vulnerabilities. Python auditing covers 104 third-party distributions with no known vulnerabilities; the local project itself is not in PyPI's audit database. Portfolio runtime dependencies were patched to Next.js 16.3.8, sharp 0.35.5 and source-map-js 1.2.2; its production-dependency audit is clean. Five pre-existing development-only alerts remain in the Next lint plugin's `fast-glob` / `micromatch` / `braces` chain. The [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) lists no patched version. The suggested forced downgrade to incompatible Next 14 lint tooling was not applied. No complete absence of security risk is inferred from dependency auditing.

The public ATLAS site uses **genuine precomputed real-data outputs**, not newly executing Python inference or SUMO. Visitors can explore all five cities, actual observations, historical forecasting evidence, synchronized control replays, twenty-seed comparison tables and pilot exports without authentication or local infrastructure. New processing remains an authenticated native backend capability; no public remote-processing SLA is claimed.

Five real application screenshots and a 57-second screen recording replace the portfolio's older ATLAS presentation. Only web resizing/compression was applied; benchmark values were not altered. [Capture/source/asset provenance](../artifacts/portfolio/v4/provenance.json).

## Remaining acceptance boundaries

All city corridors remain exploratory and independently uncalibrated. Historical observations are not fused with unrelated current snapshots. Physical queue truth, surveyed signal conflicts, natural adverse-weather holdouts, human usability and sustained remote-worker performance remain unverified. Local forecasters regress in Toronto/London; zero-shot forecasts regress in Austin/Calgary; cooperative Q control regresses in Toronto/London; the surrogate fails every city. High-demand Seattle cached/original MPC regresses against max-pressure. One Austin high-demand actuated episode has unsupported emissions/stop telemetry, with raw values and recovery records retained. No municipal savings, universal control superiority or complete commercial acceptance is claimed. See the [acceptance ledger](atlas-4-status.md) and [full measured results](atlas-4-results.md).
