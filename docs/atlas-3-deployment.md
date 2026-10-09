# Verified ATLAS 3.0 public release

Verified October 9, 2026 using the existing repositories and Vercel projects. History was preserved and neither repository was force-pushed. This publishes the verified engineering increment; the [acceptance ledger](atlas-3-status.md) retains incomplete calibration, CV, ML and human-usability criteria.

| Application | Repository | Verified production domain | Application source commit |
|---|---|---|---|
| ATLAS | [ATLAS](https://github.com/youssef061204/ATLAS) | [atlas-mu-murex.vercel.app](https://atlas-mu-murex.vercel.app) | `4e7459ff94d321ab1cc8fc0d775556a8bced7944` |
| Portfolio | [YoussefElsokkary](https://github.com/youssef061204/YoussefElsokkary) | [youssefelsokkary.vercel.app](https://youssefelsokkary.vercel.app) | `a831a8bbd933d5a1c9e155a071936afa046e8a28` |

ATLAS Vercel deployment `dpl_45MsLbtENVhg3pDNvKqXZGi1h3sy` and portfolio deployment `dpl_AZSZYsdmUC92n6XjfocrEYMQ7hrh` reached READY and received their existing production aliases. The ATLAS application code above is followed by this documentation/reproducibility update; no frontend application behavior or benchmark result changes in that follow-up.

## Actual public verification

ATLAS: **13 browser tests passed** against the production domain, with three native-only cases intentionally skipped. Checks cover the original real CV replay and twin, forecasts, benchmark artifacts, navigation, five-city catalogs, actual matched simulation replay and positions, model laboratory, zero-motor outcomes, shareable pair links, pilot export and desktop/mobile layouts. Five product areas also passed automated accessibility scans at desktop and 390px widths. The new graph artifact is publicly retrievable without authentication. An unauthenticated operational simulation POST returns **409**, making public mode explicit.

Portfolio: actual browser checks at 1440px and 390px verify ATLAS's first featured project entry, the 5.85% graph-forecasting metric, all new optimized images, the 38-second MP4, working live/source links and no page errors or failed asset responses. Lint, types and production build pass. The external link checker returns 200 for all ATLAS links and the other project references; LinkedIn returns its existing automated-access 999 response and is not claimed browser-verified.

[GitHub Actions](https://github.com/youssef061204/ATLAS/actions/runs/37902841118) completed successfully for the application commit: Python and interface jobs passed, including the city smoke and public replay checks. Expensive dataset evaluations are intentionally a separate workflow-dispatch job and did not rerun in CI. Local execution evidence separately records **107 Python**, **19 native browser**, **13 local public browser** tests, lint/types/format/build/startup, real native job cancellation/restart recovery and dependency audits with no known findings across 102 pinned Python dependencies and the npm tree.

## Hosting model and limits

The production Next.js application uses **precomputed real-output demo mode** with an empty public API base. It serves actual recorded CV results, dated official snapshot aggregates, imported attributed OSM geometry, real SUMO traces, highway forecasting artifacts and benchmark records. It does not host long-running Python, GPU inference, SUMO or persistent operations workers. New authorized processing, corrections and simulation jobs use the preserved native backend.

The city twin remains exploratory: residence/OD/signal assumptions are explicit, camera field of view and lane geometry are independently unvalidated, and the GNN remains a separate highway-domain model. Zero motor detections do not create synthetic demand. There is no live traffic hardware actuation or claim of realized municipal savings.

The original selected controller's Cologne improvement and unsuccessful transfer remain visible. The new risk-aware prototype has documented regressions and is not promoted. Public publication does not establish field calibration, queue MAE, natural-weather accuracy, human task-completion performance, an operational load SLA or completion of the unstarted learning research.
