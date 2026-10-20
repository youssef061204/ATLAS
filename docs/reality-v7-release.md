# ATLAS 7 release verification

This publishes a working, measured video/3D research system. **Physical fidelity
acceptance still fails; no new controller is promoted and no field benefit is
claimed.** [Results, comparable before/after measurements and limitations](reality-v7-results.md).

## Local verification

| Check | Observed result |
| --- | --- |
| Python | **213 passed**; Ruff check/format and backend compile checks pass |
| Public browser suite | **36 passed, 6 native-only skips**; desktop/mobile accessibility scans pass |
| Native browser flows | All six distinct native flows pass: actual cached-video overlay/seek/selection/camera setup, new portable optimization, two native paired-job flows, observation-conditioned paired simulation, and official-image region persistence/accessibility. One first navigation exceeded its 60 s test budget during a 67 s cold development compilation; the same test passes in 11.5 s after compilation. Five other native tests passed in the initial run. No application assertion or scientific gate was weakened. |
| Frontend | Lint, types, formatting and public production build pass |
| Backend | Wheel builds; final non-root Docker backend builds and starts with a 2 CPU / 2 GiB limit; health, OpenAPI and operational network endpoints respond successfully. Native paired SUMO execution works in the isolated container. User services are preserved. |
| Evidence | ATLAS 3/4/5/6/7 source/artifact verifiers pass. Version 7 checks frozen sources, all 11,220 replay frames, native outputs, physical error arithmetic, independent cohorts, live continuity, forecast chronology, rendering sources and actual media integrity. This portable audit does not rerun inference or recover private ground truth. |
| Security | Python and ATLAS frontend dependency audits: zero known findings. Portfolio production dependencies: zero findings. Five pre-existing high development lint-chain alerts remain through `braces`/`micromatch`/`fast-glob`; npm offers an incompatible framework-lint downgrade, which is not applied. |
| Portfolio | Existing architecture/design and all five projects preserved; ATLAS remains first. Lint, types and production build pass. Desktop/mobile browser checks pass for four scoped metrics, five optimized gallery images, actual walkthrough playback, links and layout; zero runtime errors or failed site assets. |
| Media | Five unaltered application screenshots and **48.4 s / 1,210 decoded frames** of actual browser recording. MP4 is 3,206,703 bytes. Exact presentation/evidence hashes and attribution/share-alike notices accompany the media. Initial loading is trimmed; scores and application frames are not fabricated. |
| Source hygiene | Raw datasets/videos, weights, model/crop/descriptor caches, transient live imagery, environments, auth files, benchmark scratch and builds remain ignored. Source archives contain actual measured code; native evidence archives contain reproducible simulation inputs/outputs. Accidental browser-regenerated legacy screenshots are restored. |

The current live CPU recheck processed 95 actual MJPEG frames (68 with tracks).
Two actually viewed daytime frames show moving trucks. The historical GPU run
remains separate: the release host currently exposes only OpenVINO CPU. Native
live workers are bounded experiments; **Vercel serves historical video and
precomputed genuine CV/SUMO results**, with no always-on inference service.

Rendering is measured separately from CV throughput. The default SwiftShader
browser improves 9.32 to 14.65 FPS at full cost and 12.46 to 19.24 FPS at reduced
cost on the same defined workload. All software-control outcomes, including an
unusually fast 60 FPS pass, remain published without a universal speed claim.
One paused replay browser memory observation is about 26 MB JavaScript heap;
this excludes peak process/GPU memory. Current complete multiscale CPU inference
throughput remains 4.803 FPS, distinct from the historical 29.4 FPS benchmark.

## Publication

Local checks above are complete. Remote commit, Linux CI and actual production
verification are recorded here after publication; this initial record does not
claim an unverified deployment succeeded.

Existing targets only:

- [ATLAS repository](https://github.com/youssef061204/ATLAS), default `main`;
  [production](https://atlas-mu-murex.vercel.app/reality), existing Vercel `atlas`
  project with `frontend` root.
- [Portfolio repository](https://github.com/youssef061204/YoussefElsokkary), default
  `main`; [production](https://youssefelsokkary.vercel.app), existing Vercel
  `youssefelsokkary` project.

No repository duplication, force push, history rewrite or paid infrastructure.
The complete scientific program is not finished: observed lamp states, accepted
free-running physical fidelity, robust cross-camera transfer, Peachtree physical
reconstruction, long-horizon forecasting and field intervention evidence remain
outstanding. No claim of globally optimal metrics is made.
