"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { request } from "@/lib/api";
import { POLICY, type Experiments, type Network, type Run } from "@/lib/cities";
import { Shell } from "./shell";
import { CityMap } from "./city-map";
import { LocalExperiment } from "./local-experiment";
import { EvidenceLoading } from "./evidence-loading";
import { readSelectedCity, selectCity } from "@/lib/city-selection";
import {
  ResponsiveContainer,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Line,
  Legend,
} from "recharts";

export function NetworkStudio() {
  const [data, setData] = useState<Experiments | null>(null);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [city, setCity] = useState("toronto");
  const [baseline, setBaseline] = useState("original_mpc");
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [activeSeed, setActiveSeed] = useState<number | null>(null);
  const [signalId, setSignalId] = useState<string | null>(null);
  const [cohort, setCohort] = useState("atlas-2");
  const [exactExperiment, setExactExperiment] = useState(false);
  useEffect(() => {
    let active = true;
    const parameters = new URL(window.location.href).searchParams;
    const selectedCity = readSelectedCity();
    const experiment = parameters.get("experiment");
    const requestedCohort =
      parameters.get("cohort") === "atlas-4" ? "atlas-4" : "atlas-2";
    Promise.all([
      experiment
        ? request<{ runs: Run[]; city: string; seed: number }>(
            `/api/operations/intelligence/${encodeURIComponent(experiment)}`,
          )
        : requestedCohort === "atlas-4"
          ? request<Experiments>("/api/operations/control-v4")
          : request<Experiments>("/api/operations/experiments"),
      request<{ networks: Network[] }>("/api/operations/networks"),
    ])
      .then(([output, n]) => {
        const paired = "seed" in output ? output : null;
        const d: Experiments =
          "scope" in output
            ? output
            : {
                scope: paired
                  ? "One actual completed observation-conditioned pair; unvalidated demand assumptions"
                  : "ATLAS 4 held-out nominal cohort; 20 paired seeds per city on exploratory generated demand. Cached MPC preserves the original traffic decisions; computational efficiency and traffic superiority are separate findings.",
                runs: output.runs,
                summaries: [],
                failures: [],
                paired: [],
              };
        if (active) {
          setData(d);
          setCohort(requestedCohort);
          setExactExperiment(!!paired);
          setNetworks(n.networks);
          if (paired) {
            setCity(paired.city);
            setActiveSeed(paired.seed);
            setBaseline(paired.runs[0].policy);
          } else if (
            selectedCity &&
            d.runs.some((r) => r.city === selectedCity)
          )
            setCity(selectedCity);
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  const candidates = data?.runs.filter((r) => r.city === city) ?? [];
  const candidate = candidates.find(
    (r) =>
      r.policy ===
        (cohort === "atlas-4" && !exactExperiment
          ? "network_mpc"
          : "risk_mpc") &&
      (activeSeed === null || r.seed === activeSeed),
  );
  const reference = candidates.find(
    (r) => r.policy === baseline && r.seed === candidate?.seed,
  );
  const frames = candidate?.trace ?? [];
  const bounded = Math.min(index, Math.max(0, frames.length - 1));
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setIndex((v) => {
          if (v >= frames.length - 1) {
            setPlaying(false);
            return v;
          }
          return v + 1;
        }),
      200,
    );
    return () => clearInterval(timer);
  }, [playing, frames.length]);
  const chart = frames.map((f, i) => ({
    t: f.t,
    prototype: f.queue,
    baseline: reference?.trace[i]?.queue,
  }));
  const network = networks.find((n) => n.city === city);
  const inspectedSignal =
    signalId ?? Object.keys(frames[bounded]?.signals ?? {})[0];
  const decision = candidate?.decisions
    .filter(
      (d) =>
        d.intersection === inspectedSignal && d.t <= (frames[bounded]?.t ?? 0),
    )
    .at(-1);
  return (
    <Shell
      title="Optimization studio"
      eyebrow="PAIRED EXPLORATORY SUMO / RECORDED RUNS"
    >
      <p className="city-notice">
        {cohort === "atlas-4" && !exactExperiment
          ? "ATLAS 4 nominal held-out cohort; generated demand and exploratory signal plans."
          : "Paired exploratory city simulations with unvalidated demand."}{" "}
        Results include regressions. These are saved executions; changing a
        replay selector does not execute a new simulation.
      </p>
      {!exactExperiment && (
        <label className="cohort-selector">
          Recorded evidence cohort
          <select
            aria-label="Recorded control cohort"
            value={cohort}
            onChange={(event) => {
              const url = new URL(window.location.href);
              url.searchParams.set("cohort", event.target.value);
              url.searchParams.set("city", city);
              window.location.assign(url.toString());
            }}
          >
            <option value="atlas-2">
              Retained ATLAS 2 study · 20 paired seeds / city
            </option>
            <option value="atlas-4">
              ATLAS 4 nominal holdout · cached MPC / 20 paired seeds
            </option>
          </select>
        </label>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="city-toolbar">
        <label>
          City{" "}
          <select
            aria-label="Simulation city"
            value={city}
            onChange={(e) => {
              selectCity(e.target.value);
              setCity(e.target.value);
              setIndex(0);
              setPlaying(false);
              setActiveSeed(null);
              setSignalId(null);
            }}
          >
            {[...new Set(data?.runs.map((r) => r.city))].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Baseline{" "}
          <select
            aria-label="Baseline controller"
            value={baseline}
            onChange={(e) => setBaseline(e.target.value)}
          >
            {[
              "fixed",
              "max_pressure",
              "original_mpc",
              ...(cohort === "atlas-4" ? ["actuated", "risk_mpc"] : []),
            ].map((p) => (
              <option key={p} value={p}>
                {POLICY[p]}
              </option>
            ))}
          </select>
        </label>
        <span>
          Paired seed {candidate?.seed ?? "—"} · {candidate?.duration ?? "—"} s
        </span>
      </div>
      {cohort === "atlas-4" && !exactExperiment && data && (
        <section className="city-panel">
          <h2>All 20 held-out seeds: {city}</h2>
          <p>
            Positive reductions mean lower delay. The replay below shows the
            first registered seed; this table summarizes the complete nominal
            cohort.
          </p>
          <div
            className="table-wrap"
            role="region"
            aria-label="Held-out controller results"
            tabIndex={0}
          >
            <table aria-label="Held-out controller comparison">
              <thead>
                <tr>
                  <th>Controller</th>
                  <th>Mean delay</th>
                  <th>Paired reduction vs {POLICY[baseline]}</th>
                  <th>95% bootstrap interval</th>
                </tr>
              </thead>
              <tbody>
                {data.summaries
                  .filter((row) => row.city === city)
                  .map((row) => {
                    const comparison = row.comparisons?.find(
                      (item) => item.baseline === baseline,
                    );
                    return (
                      <tr key={row.policy}>
                        <td>{POLICY[row.policy] ?? row.policy}</td>
                        <td>{row.mean_delay_s.toFixed(2)} s</td>
                        <td>
                          {comparison
                            ? `${comparison.mean_paired_reduction_pct.toFixed(2)}%`
                            : "Not computed"}
                        </td>
                        <td>
                          {comparison
                            ? `${comparison.ci95[0].toFixed(2)} to ${comparison.ci95[1].toFixed(2)}%`
                            : "Not computed"}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <a
            className="button secondary"
            href="https://github.com/youssef061204/ATLAS/tree/main/artifacts/cities/v4"
            target="_blank"
            rel="noopener noreferrer"
          >
            Inspect every seed and lossless raw evidence
          </a>
          <p>
            <Link
              className="button secondary"
              href={`/pilot?city=${city}&cohort=atlas-4`}
            >
              Build a pilot assessment from all 20 paired seeds
            </Link>
          </p>
        </section>
      )}
      <div className="studio-content-area" aria-busy={!data && !error}>
        {!data && !error && (
          <EvidenceLoading label="Loading actual paired experiment evidence…" />
        )}
        {candidate && reference ? (
          <>
            <div className="city-columns">
              {[reference, candidate].map((r) => (
                <section className="city-panel" key={r.policy}>
                  <h2>{POLICY[r.policy]}</h2>
                  <CityMap
                    key={city + r.policy}
                    network={network}
                    frame={r.trace[bounded]}
                  />
                  <div className="city-metrics">
                    <div>
                      <span>DELAY</span>
                      <strong>{r.metrics.mean_delay_s.toFixed(2)} s</strong>
                    </div>
                    <div>
                      <span>QUEUE NOW</span>
                      <strong>{r.trace[bounded]?.queue ?? "—"}</strong>
                    </div>
                    <div>
                      <span>THROUGHPUT</span>
                      <strong>
                        {r.metrics.throughput_vehicles_per_hour.toFixed(0)} /h
                      </strong>
                    </div>
                  </div>
                </section>
              ))}
            </div>
            <div className="city-toolbar">
              <button className="button" onClick={() => setPlaying((v) => !v)}>
                {playing ? "Pause replay" : "Play recorded comparison"}
              </button>
              <label className="city-timeline">
                Replay time {frames[bounded]?.t} s
                <input
                  type="range"
                  aria-label="Network replay timeline"
                  min="0"
                  max={Math.max(0, frames.length - 1)}
                  value={bounded}
                  onChange={(e) => {
                    setIndex(Number(e.target.value));
                    setPlaying(false);
                  }}
                />
              </label>
            </div>
            <section className="city-panel">
              <h2>Simulated queues on controlled approaches</h2>
              <div style={{ height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chart}>
                    <CartesianGrid stroke="#263a42" />
                    <XAxis dataKey="t" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line
                      dataKey="baseline"
                      name={POLICY[baseline]}
                      stroke="#94a5ae"
                      dot={false}
                    />
                    <Line
                      dataKey="prototype"
                      name={POLICY[candidate.policy]}
                      stroke="#70c9bc"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
            <div className="city-columns">
              <section className="city-panel">
                <h2>Decision inspection</h2>
                <label>
                  Intersection
                  <select
                    aria-label="Inspect simulated intersection"
                    value={inspectedSignal ?? ""}
                    onChange={(e) => setSignalId(e.target.value)}
                  >
                    {Object.keys(frames[bounded]?.signals ?? {}).map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
                {decision ? (
                  <>
                    <p>
                      Intersection {decision.intersection} · computed at{" "}
                      {decision.t} s
                    </p>
                    <p>
                      Phase {decision.selected} · {decision.reason}
                    </p>
                    <p>
                      {decision.reason === "small_phase_pressure_fallback"
                        ? "The declared max-pressure fallback selected this phase for a small phase layout. The risk-aware search was not used for this action."
                        : decision.reason === "invalid_sensor_fallback"
                          ? "Required sensor state was unavailable or invalid. The controller deferred to the deterministic safety fallback."
                          : decision.reason === "risk_aware_fluid_search"
                            ? "The bounded search compared permitted phase sequences using modeled queue growth, downstream capacity, tail risk and waiting time."
                            : decision.reason === "cached_network_fluid_search"
                              ? "Cached topology and batched fluid lookahead compare the independently permitted phases. This nominal candidate preserves the original MPC traffic decisions; a lower computation cost does not imply a traffic-outcome gain over that baseline."
                              : "This action follows the recorded controller logic and its permitted-action set."}
                    </p>
                    <p>
                      Planning horizon: {decision.horizon_s ?? "Fallback"} s ·
                      fluid objective:{" "}
                      {(
                        decision.objective ?? decision.fluid_objective
                      )?.toFixed(2) ?? "Not applicable"}
                    </p>
                    <p>Permitted actions: {decision.constraints.join(", ")}</p>
                    <p>
                      Arrival envelopes:{" "}
                      {decision.arrival_uncertainty?.join(" / ") ??
                        "Not modeled"}
                      . These are assumed scenarios, not calibrated
                      probabilities.
                    </p>
                    <ul>
                      {(decision.alternatives ?? []).map((a) => (
                        <li key={a.phase}>
                          Phase {a.phase}: first-stage objective{" "}
                          {a.first_stage_cost.toFixed(2)}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <p>
                    No optimization decision logged at this replay time;
                    minimum-green or clearance may bind.
                  </p>
                )}
                <p>
                  Inspection describes the actual recorded computation. Agency
                  timing/conflict validation and physical signal hardware
                  integration are pending.
                </p>
              </section>
              <section className="city-panel">
                <h2>Measured tradeoffs</h2>
                <dl className="city-details">
                  {[
                    [
                      "Delay difference",
                      `${(reference.metrics.mean_delay_s - candidate.metrics.mean_delay_s).toFixed(2)} s; positive means lower prototype delay`,
                    ],
                    [
                      "Prototype median delay",
                      `${candidate.metrics.median_delay_s.toFixed(2)} s`,
                    ],
                    [
                      "Prototype completed trips",
                      `${candidate.metrics.completed_trips} / ${candidate.metrics.scheduled_vehicles}`,
                    ],
                    [
                      "Prototype stops / vehicle",
                      typeof candidate.metrics.stops_per_vehicle === "number"
                        ? candidate.metrics.stops_per_vehicle.toFixed(2)
                        : "Unavailable: invalid subscription telemetry",
                    ],
                    [
                      "SUMO modeled CO₂",
                      typeof candidate.metrics.co2_model_kg === "number"
                        ? `${candidate.metrics.co2_model_kg.toFixed(3)} kg`
                        : "Unavailable: invalid subscription telemetry",
                    ],
                    [
                      "Controller p95",
                      `${candidate.metrics.decision_ms_p95.toFixed(3)} ms`,
                    ],
                    [
                      "Modeled invariant violations",
                      String(candidate.metrics.modeled_safety_violations),
                    ],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                <p>
                  Emissions use SUMO's vehicle model. Pedestrian/transit delay
                  and person occupancy were not measured in these passenger-car
                  scenarios.
                </p>
              </section>
            </div>
          </>
        ) : (
          data && <p>No paired completed experiment for this selection.</p>
        )}
      </div>
      <details className="city-panel">
        <summary>Technical reproduction details</summary>
        <p>
          Recorded replay is available immediately. New execution uses a
          configured Python worker.
        </p>
        <code>python scripts/benchmark_cities.py --city {city} --seeds 20</code>
      </details>
      {data && (
        <LocalExperiment
          city={city}
          baseline={baseline}
          candidate={
            cohort === "atlas-4" && !exactExperiment
              ? "network_mpc"
              : "risk_mpc"
          }
          onComplete={(runs) => {
            setData((previous) =>
              previous
                ? { ...previous, runs: [...previous.runs, ...runs] }
                : previous,
            );
            setActiveSeed(runs[0].seed);
            setIndex(0);
            setPlaying(false);
          }}
        />
      )}
    </Shell>
  );
}
