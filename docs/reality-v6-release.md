# Continuous-video milestone release verification

Status: local verification complete; remote and production verification pending.
This releases a working measured baseline, **not accepted physical fidelity or a completed ATLAS 6 scientific validation program**. [Results and remaining gates](reality-v6-results.md).

| Check | Observed result |
| --- | --- |
| Python | **186 passed**, one dependency deprecation warning |
| Frontend | Lint, types, formatting and native/public production builds pass |
| Complete public browser suite | **32 passed, 6 native-only skips**, no failures; desktop/mobile accessibility scans pass |
| Native browser subset | 19 distinct checks pass, 4 private/operator-dependent skips. Two initial timeouts under concurrent CV load pass immediately on isolated rerun; these are recorded as transient failures, not erased. |
| Backend package | Wheel builds; compile check passes |
| Final Docker image | `atlas-v6-final` builds; startup `/health` succeeds, v6 modules import, non-root UID 10001, 2 CPU / 2 GiB smoke limit |
| Evidence | ATLAS 3/4/5 verifiers pass; v6 verifies all 11,220 presentation frames, native positions, source/protocol hashes, metric arithmetic, partial holdout, CityFlow regression and actual dated HLS telemetry |
| Security | Installed Python dependencies: no known findings (local project excluded from registry audit). ATLAS frontend: zero production/development findings. Portfolio: zero production findings; five pre-existing high development lint-chain alerts remain. npm's forced fix would downgrade framework lint tooling and was not applied. |
| Media | Four unaltered actual application screenshots; **41 s / 1,025 decoded frames** of current screen recording, 1,108,951-byte MP4; provenance and FHWA attribution/license included |
| Source hygiene | Raw source videos/tables/support archives, model weights, local results, temporary HLS buffers, environments and build outputs remain ignored. Only licensed web-video adaptation, aggregate/derived outputs and actual application media are intended for publication. |

Existing repositories/projects are reused: `youssef061204/ATLAS`, `youssef061204/YoussefElsokkary`, Vercel `atlas` (`frontend`) and `youssefelsokkary` (`.`), both on the existing team. No new repository, paid service or infrastructure was created. No force push or history rewrite is permitted.

Public mode is historical video with precomputed actual CV/native SUMO output. The dated native Caltrans HLS trial decoded 1,740 frames but predicted zero nighttime tracks; it does not host or validate an always-on public live camera. The complete NGSIM video works, while reconstruction and multicamera association fail their scientific acceptance goals. Exact lane/turn accuracy, observed lamp states, paired travel times, complete final holdout, accepted physical twins and field benefits remain outstanding.
