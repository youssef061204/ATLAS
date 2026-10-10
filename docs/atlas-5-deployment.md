# ATLAS 5 verified engineering release

Both existing repositories and production projects were reused. History is preserved;
no force push, duplicate repository or new hosting service was introduced.

| Application | Verified production URL | Application commit | Production deployment |
| --- | --- | --- | --- |
| ATLAS | https://atlas-mu-murex.vercel.app | `616805cc9edd7340ec742de2f9a46bf43b7edff4` | `dpl_BnyFgnBFeGCVPDRzgud6WnTjnnQK` |
| Portfolio | https://youssefelsokkary.vercel.app | `4f1d16c9db0e4baf614d228620c79ddd6d6094d6` | `dpl_CjG448m5qTfqVfxmXjKMV71NA2fa` |

Platform metadata verifies the intended project IDs, production aliases, main
branches and exact application commits. Subsequent documentation/evidence commits
preserve the deployed frontend, backend and published demo-input trees. The final
repository HEAD and deployment are inspected again after those commits.

## Actual verification

- **153 Python tests** pass; one existing Starlette/httpx deprecation warning remains.
- **30 native browser tests** pass, with five public-demo-only cases intentionally
  skipped. Actual operator jobs, CV overlay/selection, source-region correction,
  original/cached SUMO execution and pilot export are exercised.
- **29 public browser tests** pass against the actual unauthenticated ATLAS production
  domain, with six native-only cases intentionally skipped. Landing/workspace,
  digital twin, charts, benchmark pages, all five calibration views, all 30
  city/scenario comparisons and genuine ten-seed pilot exports work.
- **53 production HTTP integrity checks** pass: committed calibration/forecast/
  geometry, all 30 replay studies, six pilot cohorts, five count series and six
  portfolio media files match published evidence. Three native mutation routes
  reject public processing with HTTP 409.
- Desktop and mobile production portfolio browsers verify ATLAS prominence, four
  scoped metrics, five optimized images, actual video playback, live/GitHub links,
  and zero runtime errors or horizontal overflow. Every ATLAS documentation/live
  link returns HTTP 200; LinkedIn blocks the separate global link checker with 999.
- Frontend lint, types, formatting and native/public builds pass. Backend lint,
  formatting, compilation and wheel build pass. A fresh nonroot Docker image,
  limited to two CPUs, 2 GiB RAM and 128 PIDs, passes actual 480-frame upload,
  reprocessing, SSE, replay, database and metrics checks plus four native SUMO smoke
  episodes. Its completed task-owned smoke container is stopped afterward.
- All v3/v4/v5 evidence verifiers pass locally and in
  [GitHub CI](https://github.com/youssef061204/ATLAS/actions/runs/38081726595).
  CI includes Linux tests/builds, lossless raw episode verification and actual SUMO.

Initial aggregate accessibility checks exceeded their shared-host scan budget.
The trace showed individual successful scans; freeing the completed smoke container
and extending the ten-scan aggregate budget resolved this. All assertions remain
enabled. The final suites have zero unexpected failures or flaky outcomes.

## Measured UX and real media

Thirty city/view/viewport production-build scans report zero automated accessibility
violations, page errors, failed responses or horizontal overflow. Bundled licensed
fonts and reserved loading space reduce maximum observed local CLS from 0.567 to
0.024. A separate throttled Lighthouse sample scores **97 performance / 100
accessibility / 100 best practices / 100 SEO**, with CLS 0.0006 and LCP 2.665 seconds.
Its LCP is slightly higher than the initial sample. One observation per case does
not establish statistical speedup, field Core Web Vitals or human usability.
Participants remain **0**; the prospective study protocol is published.

Five authentic application screenshots are 90–147 KB each. The current silent
walkthrough is **36 seconds / 843,727 bytes** and includes real CV, count evidence,
actual matched optimization replay and benchmarks. Only encoding, resizing and
loading-footage trimming were applied; no application values were altered.

## Security and execution boundary

The ATLAS frontend audit and the audit of **102 pinned Python distributions** report
no known vulnerabilities. The portfolio production-dependency audit is clean.
Five pre-existing development-only alerts remain in its Next lint-tool chain;
an incompatible forced downgrade was not applied. Audits are snapshots, not a
security guarantee. Secrets, environments, restricted datasets, model caches,
dependencies, builds and scratch runs are excluded from source control. The
published 75 lossless benchmark bundles are deliberate research evidence.

Public ATLAS uses **precomputed legitimate processing and simulation outputs**.
It does not newly run Python inference or SUMO on Vercel. The authenticated durable
native execution architecture passes actual private SUMO/account/quota/cancellation
checks and remains disabled publicly. No new paid worker was provisioned:
incremental hosted-worker spend is **$0**; existing account charges and electricity
are unmeasured. TLS, retention, kernel resource boundaries, observability and
reviewed hosting costs remain prerequisites for a public native service.

## Scientific acceptance remains limited

All five twins remain Level 1 exploratory models: **0 independently validated
corridors/intersections and 0 observed field benefits**. Demand reconstruction is
not measured simulator-state accuracy. Whitehall demand reconstruction fails;
Austin zero-shot transfer worsens; the portfolio loses to cached/original MPC and
fails its worst-episode guard despite average fixed/max-pressure gains. Its policy
is not promoted. City lane/queue labels, coeval calibrated sensors, surveyed timing/
conflict/pedestrian plans, independent dynamic holdouts and human/agency oversight
remain missing. The release supports technical demonstration and data-readiness
planning, not a commercial or operational municipal-benefit claim.

See [acceptance ledger](atlas-5-status.md), [measured results](atlas-5-results.md),
[resume evidence](atlas-5-resume-bullets.md), and the local/production/CI/deployment
verification records in [`artifacts/cities/v5`](../artifacts/cities/v5).
