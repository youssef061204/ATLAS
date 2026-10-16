# Continuous-video milestone release verification

Status: existing remote repositories and both production deployments verified on October 16, 2026.
This releases a working measured baseline, **not accepted physical fidelity or a completed ATLAS 6 scientific validation program**. [Results and remaining gates](reality-v6-results.md).

| Check | Observed result |
| --- | --- |
| Python | **186 passed**, one dependency deprecation warning |
| Frontend | Lint, types, formatting and native/public production builds pass |
| Complete public browser suite | **32 passed, 6 native-only skips**, no failures; desktop/mobile accessibility scans pass |
| Actual ATLAS production browser checks | **8 passed**: navigation/assets, real replay, charts, controller playback, video/SUMO synchronization, mobile accessibility and unavailable-evidence handling |
| Actual portfolio production checks | Desktop/mobile pass; ATLAS remains first of five projects; five optimized gallery images and the 41-second walkthrough load/play; zero page errors or failed site assets. Published new media match source bytes. A real click through portfolio → ATLAS → synchronized video playback succeeds. |
| Native browser subset | 19 distinct checks pass, 4 private/operator-dependent skips. Two initial timeouts under concurrent CV load pass immediately on isolated rerun; these are recorded as transient failures, not erased. |
| Backend package | Wheel builds; compile check passes |
| Final Docker image | `atlas-v6-final` builds; startup `/health` succeeds, v6 modules import, non-root UID 10001, 2 CPU / 2 GiB smoke limit |
| Evidence | ATLAS 3/4/5 verifiers pass; v6 verifies all 11,220 presentation frames, native positions, source/protocol hashes, metric arithmetic, partial holdout, CityFlow regression and actual dated HLS telemetry |
| Security | Installed Python dependencies: no known findings (local project excluded from registry audit). ATLAS frontend: zero production/development findings. Portfolio: zero production findings; five pre-existing high development lint-chain alerts remain. npm's forced fix would downgrade framework lint tooling and was not applied. |
| Media | Four unaltered actual application screenshots; **41 s / 1,025 decoded frames** of current screen recording, 1,108,951-byte MP4; provenance and FHWA attribution/license included |
| Source hygiene | Raw source videos/tables/support archives, model weights, local results, temporary HLS buffers, environments and build outputs remain ignored. Only licensed web-video adaptation, aggregate/derived outputs and actual application media are intended for publication. |

Existing repositories/projects are reused: `youssef061204/ATLAS`, `youssef061204/YoussefElsokkary`, Vercel `atlas` (`frontend`) and `youssefelsokkary` (`.`), both on the existing team. No new repository, paid service or infrastructure was created. No force push or history rewrite is permitted.

## Published versions

- [ATLAS implementation commit](https://github.com/youssef061204/ATLAS/commit/aceb4013efea590e42180e143855a3c3a7827722): `aceb4013efea590e42180e143855a3c3a7827722`, confirmed equal to remote `main` and default HEAD before this verification/documentation follow-up. [Linux CI](https://github.com/youssef061204/ATLAS/actions/runs/38860633061): Python and interface jobs succeed; optional expensive dataset re-evaluation is intentionally skipped.
- [ATLAS production](https://atlas-mu-murex.vercel.app/reality): existing Vercel project, production deployment `dpl_Cj7fQeuJzgnqBQok8s6KnPYqTCam` reports Ready with that exact Git SHA. Landing, video experiment, benchmarks and architecture return 200 without authentication. The remote manifest, eight evidence/media assets and synchronized chunk match local verified bytes. Video Range returns **206** with the correct 27,889,989-byte complete-file length.
- [Portfolio commit](https://github.com/youssef061204/YoussefElsokkary/commit/151e8b8a09530e4b33362ba97a770cc1874960b1): `151e8b8a09530e4b33362ba97a770cc1874960b1`, confirmed equal to remote `main` and default HEAD.
- [Portfolio production](https://youssefelsokkary.vercel.app): existing project, production deployment `dpl_BeDRxk2kpYhQB9uo5qDEE6iN5npB` reports Ready with that exact Git SHA. Live demo, source and evidence/license links are verified. The existing unrelated LinkedIn endpoint blocks automated link checking with status 999; all ATLAS links return 200.

This verification/documentation follow-up leaves application and measured artifact bytes unchanged. Its Git commit may follow the implementation commit above; the final remote tip and its subsequent production deployment are checked separately after push. The existing Vercel team is confirmed **Hobby**.

Public mode is historical video with precomputed actual CV/native SUMO output. The dated native Caltrans HLS trial decoded 1,740 frames but predicted zero nighttime tracks; it does not host or validate an always-on public live camera. The complete NGSIM video works, while reconstruction and multicamera association fail their scientific acceptance goals. Exact lane/turn accuracy, observed lamp states, paired travel times, complete final holdout, accepted physical twins and field benefits remain outstanding.
