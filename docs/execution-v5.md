# Bounded experiment execution

ATLAS preserves the existing public replay and authenticated native CV/SUMO
workflows. The additional `/api/execution` service supports **new native paired
SUMO experiments**. It remains disabled by default and is not publicly hosted.
Vercel continues to serve genuine precomputed processing and simulation results.

Enable `ATLAS_EXECUTION_ENABLED=true` only on an isolated native service. Configure
`ATLAS_EXECUTION_KEYS` as a private JSON mapping of account identifiers to separate
high-entropy API credentials, using the hosting provider's secret configuration.
Do not put credentials in public Next.js variables or tracked files. The worker
child environment excludes the account credentials and existing operator key.

The service accepts only five restored city networks, one seed, two paired episodes,
60–300 simulated seconds, three bounded scenarios, and existing fixed/max-pressure/
original/cached-MPC policies. The new experimental portfolio is not promoted into
this service. No request can submit a shell command, Python import, network path,
arbitrary controller or external URL.

Controls implemented:

- Account-scoped submissions, status, results and cancellation; another account
  gets HTTP 404 for a private job even when it knows the job identifier.
- SQLite transactions enforce five accepted submissions per UTC day per account,
  a five-second submission interval, two active jobs per account and eight globally.
  Accepted cancellations consume quota; restarting cannot reset it.
- One supervisor executes queued jobs serially. Each job uses a fresh process,
  one native numerical thread, a 60-second wall deadline and a monitored 2 GiB
  aggregate RSS ceiling for the worker and its SUMO descendants.
- Cancellation and timeout terminate only the job's owned process tree. Container
  CPU/PID/disk limits remain deployment requirements; RSS monitoring is not a kernel
  memory sandbox. Use one supervisor per execution database.
- Durable status, progress, private error logs and worker heartbeat. A restart marks
  queued/running jobs interrupted rather than silently repeating them.
- Deterministic experiment identity from parameters and version/network provenance,
  unique attempt identifiers, a 20 MB result budget and SHA-256 result verification.

`scripts/verify_execution_v5.py` checks the actual FastAPI lifecycle with two real
SUMO episodes, paired inputs, signal safety, rejected unauthorized/cross-account
requests, rate limiting and cancellation. It uses separate verification storage
and explicitly synthetic local credentials. Unit tests additionally exercise
concurrent quota reservation, persistence and termination of a real worker process.

## Hosting and cost boundary

No additional paid service has been provisioned. This increment's incremental
hosting charge is zero; existing Vercel/account costs and local electricity are
not measured. A paid deployment requires a documented provider configuration,
container resource limits, durable storage and backup, credential rotation,
retention/disk quotas, monitoring and a measured workload cost budget. Native
verification does not prove public worker reachability or hosted reliability.

CV uploads remain in the existing operator workflow. Exposing new hosted CV jobs
would require separate upload/model/download/storage quotas and resource validation.
The simulation service does not make that unverified capability public.
