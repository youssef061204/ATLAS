"use client";
import { useRef, useState } from "react";
import { DEMO_MODE, request } from "@/lib/api";
import type { Run } from "@/lib/cities";

type Job = { id: string; state: string; error?: string; result_path?: string };
export function LocalExperiment({
  city,
  baseline,
  onComplete,
}: {
  city: string;
  baseline: string;
  onComplete: (runs: Run[]) => void;
}) {
  const [key, setKey] = useState("");
  const [seed, setSeed] = useState(19001);
  const [risk, setRisk] = useState(0.2);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const activeJob = useRef<{ id: string; key: string } | null>(null);
  const [canCancel, setCanCancel] = useState(false);
  async function cancel() {
    const job = activeJob.current;
    if (!job) return;
    try {
      await request(`/api/operations/jobs/${job.id}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${job.key}` },
      });
      setStatus(
        "Cancellation requested; waiting for the simulation worker to stop.",
      );
    } catch (e) {
      setStatus(
        e instanceof Error ? e.message : "Cancellation could not be requested",
      );
    }
  }
  async function execute() {
    setBusy(true);
    setStatus("Submitting matched local simulations…");
    const supplied = key;
    setKey("");
    try {
      const runs: Run[] = [];
      for (const policy of [baseline, "risk_mpc"]) {
        const job = await request<Job>("/api/operations/experiments", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${supplied}`,
          },
          body: JSON.stringify({
            city,
            policy,
            seed,
            duration: 300,
            risk_weight: risk,
          }),
        });
        let state = job;
        activeJob.current = { id: job.id, key: supplied };
        setCanCancel(true);
        const deadline = Date.now() + 120000;
        while (
          !["complete", "failed", "cancelled", "interrupted"].includes(
            state.state,
          )
        ) {
          if (Date.now() > deadline)
            throw new Error(
              `Job ${job.id} is still running; its status is retained in the local API.`,
            );
          await new Promise((resolve) => setTimeout(resolve, 800));
          state = await request<Job>(`/api/operations/jobs/${job.id}`);
          setStatus(`${policy}: ${state.state}`);
        }
        if (state.state !== "complete" || !state.result_path)
          throw new Error(state.error ?? "Simulation failed");
        runs.push(await request<Run>(state.result_path));
      }
      if (
        runs[0].network_sha256 !== runs[1].network_sha256 ||
        runs[0].routes_sha256 !== runs[1].routes_sha256
      )
        throw new Error(
          "Inputs changed between simulations; paired comparison rejected",
        );
      onComplete(runs);
      setStatus(
        "Two new simulations completed. Their actual outputs are selected in the replay.",
      );
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Execution failed");
    } finally {
      activeJob.current = null;
      setCanCancel(false);
      setBusy(false);
    }
  }
  if (DEMO_MODE)
    return (
      <p>
        New runs require the local Python/SUMO worker. Public replay remains
        read-only.
      </p>
    );
  return (
    <section className="city-panel">
      <h2>Execute a matched local experiment</h2>
      <p>
        Runs the pinned OSM corridor with assumed demand. Objective changes are
        experimental; safety constraints remain mandatory. Operational writes
        require a configured local operator key.
      </p>
      <div className="city-toolbar">
        <label>
          Operator key
          <input
            aria-label="Operator key"
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <label>
          Simulation seed
          <input
            aria-label="Simulation seed"
            type="number"
            min="1"
            value={seed}
            onChange={(e) => setSeed(Math.max(1, Number(e.target.value)))}
          />
        </label>
        <label>
          Tail-risk weight
          <input
            aria-label="Tail-risk weight"
            type="number"
            min="0"
            max="5"
            step=".1"
            value={risk}
            onChange={(e) =>
              setRisk(Math.min(5, Math.max(0, Number(e.target.value))))
            }
          />
        </label>
        <button className="button" disabled={!key || busy} onClick={execute}>
          {busy ? "Running simulations…" : "Run new paired simulation"}
        </button>
        {canCancel && (
          <button className="button secondary" onClick={cancel}>
            Cancel simulation
          </button>
        )}
      </div>
      <p role="status">{status}</p>
    </section>
  );
}
