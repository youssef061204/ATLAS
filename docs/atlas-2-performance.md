# Performance and deployment profiles

`python scripts/profile_v2.py` measures matched synthetic 8-movement states, 100 decisions per controller, p50/p95 latency, sampled process RSS and coarse process CPU-time windows. Inputs are paired by seed. Process CPU percentage may exceed 100% for multi-threaded work and is noisy at 20-decision sampling windows; it is not host CPU utilization. RSS includes imported Python dependencies. The experimental search can be **slower** than frozen MPC; this increment claims no universal computation improvement.

Network artifacts record actual decision p50/p95 and simulation steps/s. Benchmark wall times collected while independent jobs/builds run are contention-sensitive; do not use them as dedicated-hardware SLA or cost forecasts. Existing UA-DETRAC 29.4 FPS retains its original hardware/dataset scope; snapshot latency and cold model loading do not replace that throughput measurement.

An edge research profile uses one CPU worker, two admitted simulation jobs, two ingestion slots and sparse snapshot processing. A regional profile can run independent scenarios in separate worker containers with bounded queues and shared aggregate provenance; cross-host deduplication, durable scheduling and coordinated deployment recovery remain future engineering. No Kafka/Kubernetes is introduced.

Operating costs in the pilot calculator are explicit user assumptions. This is not a hosted-backend price quote or validated commercial TCO. Simulation runtime needs an appropriate Python/SUMO worker; static Vercel hosting has no such worker. Long-running jobs are never implemented as static-frontend functions.
