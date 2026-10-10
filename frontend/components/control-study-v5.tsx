"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { CITY_CHOICES, useCitySelection } from "@/lib/city-selection";
import { POLICY, type Experiments, type Network, type Run } from "@/lib/cities";
import { Shell } from "./shell";
import { CityMap } from "./city-map";

type Study = Experiments & {
  case: string;
  seed_count: number;
  production_promoted: boolean;
  promotion_checks: Record<string, boolean>;
};
const CASES = [
  ["low", "Low demand"],
  ["nominal", "Nominal demand"],
  ["high", "High demand"],
  ["incident", "Lane closure"],
  ["outage", "Sensor outage"],
  ["shift", "Bursty demand shift"],
] as const;
const number = (value: unknown, digits = 2) =>
  typeof value === "number" ? value.toFixed(digits) : "Unavailable";

export function ControlStudyV5() {
  const [city, selectCity] = useCitySelection();
  const [scenario, setScenario] = useState("nominal");
  const [data, setData] = useState<Study | null>(null);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [baseline, setBaseline] = useState("max_pressure");
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [signal, setSignal] = useState("");
  const [error, setError] = useState("");
  const [geometryError, setGeometryError] = useState("");
  useEffect(() => {
    const value = new URL(window.location.href).searchParams.get("case");
    if (CASES.some(([key]) => key === value)) setScenario(value!);
  }, []);
  useEffect(() => {
    let active = true;
    request<{ networks: Network[] }>("/api/operations/networks")
      .then((value) => {
        if (active) setNetworks(value.networks);
      })
      .catch(() => {
        if (active)
          setGeometryError(
            "Road geometry is currently unavailable; recorded metrics remain inspectable.",
          );
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    fetch(`/demo/cities/v5/studio-${city}-${scenario}.json`, {
      signal: abort.signal,
    })
      .then((response) => {
        if (!response.ok)
          throw new Error("This recorded comparison is unavailable");
        return response.json() as Promise<Study>;
      })
      .then((value) => {
        if (!abort.signal.aborted) {
          setData(value);
          setError("");
        }
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setError(e instanceof Error ? e.message : "Evidence unavailable");
      });
    return () => abort.abort();
  }, [city, scenario]);
  const current =
    data?.case === scenario && data.runs[0]?.city === city ? data : null;
  const candidate = current?.runs.find((row) => row.policy === "portfolio_v5");
  const reference = current?.runs.find((row) => row.policy === baseline);
  const frames = candidate?.trace ?? [];
  const bounded = Math.min(index, Math.max(0, frames.length - 1));
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () => setIndex((previous) => (previous + 1) % Math.max(1, frames.length)),
      250,
    );
    return () => clearInterval(timer);
  }, [playing, frames.length]);
  const inspected =
    signal in (frames[bounded]?.signals ?? {})
      ? signal
      : Object.keys(frames[bounded]?.signals ?? {})[0];
  const decision = candidate?.decisions
    .filter(
      (row) =>
        row.intersection === inspected && row.t <= (frames[bounded]?.t ?? 0),
    )
    .at(-1) as
    | (Run["decisions"][number] & {
        family?: string;
        inbound_occupancy_fraction?: number;
      })
    | undefined;
  const network = networks.find((row) => row.city === city);
  const selectedSummary = current?.summaries.find(
    (row) => row.policy === "portfolio_v5",
  );
  const comparison = selectedSummary?.comparisons?.find(
    (row) => row.baseline === baseline,
  );
  function changeScenario(value: string) {
    setScenario(value);
    setIndex(0);
    setPlaying(false);
    setSignal("");
    const url = new URL(window.location.href);
    url.searchParams.set("case", value);
    window.history.replaceState(null, "", url);
  }
  return (
    <Shell
      title="Robust control comparison"
      eyebrow="ATLAS 5 / ACTUAL PAIRED SUMO / EXPLORATORY"
    >
      <div className="city-panel calibration-hero">
        <span className="city-status">
          EXPERIMENTAL · PRODUCTION POLICY UNCHANGED
        </span>
        <h2>Compare traffic strategies under stress.</h2>
        <p>
          2,100 genuine held-out episodes across five cities, six scenario
          families and seven controllers. The selector uses current lane
          occupancy; average gains did not satisfy the worst-episode promotion
          guard.
        </p>
        <div className="calibration-journey">
          <Link href={`/calibration?city=${city}`}>
            Inspect twin validation
          </Link>
          <Link href={`/studio?city=${city}&cohort=atlas-4`}>
            Retained ATLAS 4 study
          </Link>
          <Link href={`/pilot?city=${city}&cohort=atlas-5&case=${scenario}`}>
            Export this pilot assessment
          </Link>
        </div>
      </div>
      <div className="city-toolbar">
        <label>
          City
          <select
            aria-label="Simulation city"
            value={city}
            onChange={(event) => {
              selectCity(event.target.value);
              setIndex(0);
              setPlaying(false);
              setSignal("");
            }}
          >
            {CITY_CHOICES.map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Scenario
          <select
            aria-label="Robustness scenario"
            value={scenario}
            onChange={(event) => changeScenario(event.target.value)}
          >
            {CASES.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Baseline
          <select
            aria-label="Baseline controller"
            value={baseline}
            onChange={(event) => setBaseline(event.target.value)}
          >
            {[
              "fixed",
              "max_pressure",
              "original_mpc",
              "cached_original",
              "actuated",
              "cooperative_q",
            ].map((policy) => (
              <option key={policy} value={policy}>
                {POLICY[policy] ?? policy}
              </option>
            ))}
          </select>
        </label>
      </div>
      {geometryError && <p role="alert">{geometryError}</p>}
      {error && <p role="alert">{error}</p>}
      {!current && !error && (
        <div
          className="city-panel evidence-reserved"
          role="status"
          aria-busy="true"
        >
          Loading actual paired experiment…
        </div>
      )}
      {current && (
        <>
          <section className="city-panel">
            <h2>
              All {current.seed_count} paired final seeds: {city} / {scenario}
            </h2>
            <p>
              Positive reductions mean lower mean delay. The interval describes
              simulator seed variation. The twin remains unvalidated against
              independent real-world dynamics.
            </p>
            <div
              className="calibration-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Scroll controller comparisons"
            >
              <table aria-label="Held-out controller comparison">
                <thead>
                  <tr>
                    <th scope="col">Controller</th>
                    <th scope="col">Mean delay</th>
                    <th scope="col">Reduction vs baseline</th>
                    <th scope="col">95% paired interval</th>
                  </tr>
                </thead>
                <tbody>
                  {current.summaries.map((row) => {
                    const measured = row.comparisons?.find(
                      (item) => item.baseline === baseline,
                    );
                    return (
                      <tr
                        key={row.policy}
                        className={
                          row.policy === "portfolio_v5" ? "selected" : ""
                        }
                      >
                        <th scope="row">{POLICY[row.policy] ?? row.policy}</th>
                        <td>{number(row.mean_delay_s)} s</td>
                        <td>{number(measured?.mean_paired_reduction_pct)}%</td>
                        <td>
                          {measured
                            ? `${number(measured.ci95[0])} to ${number(measured.ci95[1])}%`
                            : "Unavailable"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {comparison && (
              <p
                className={
                  comparison.mean_paired_reduction_pct < 0
                    ? "forecast-regression"
                    : "calibration-note"
                }
              >
                Portfolio vs {POLICY[baseline]}:{" "}
                {number(comparison.mean_paired_reduction_pct)}% paired mean
                delay reduction.{" "}
                {comparison.mean_paired_reduction_pct < 0
                  ? "This cell regressed."
                  : comparison.ci95[0] <= 0
                    ? "The interval includes no benefit."
                    : "Measured in exploratory simulation."}
              </p>
            )}
          </section>
          {candidate && reference && (
            <>
              <div className="city-columns">
                {[reference, candidate].map((row) => (
                  <section className="city-panel" key={row.policy}>
                    <h2>{POLICY[row.policy] ?? row.policy}</h2>
                    <CityMap network={network} frame={row.trace[bounded]} />
                    <div className="city-metrics">
                      <div>
                        <span>REPLAY MEAN DELAY</span>
                        <strong>{number(row.metrics.mean_delay_s)} s</strong>
                      </div>
                      <div>
                        <span>QUEUE AT THIS TIME</span>
                        <strong>
                          {row.trace[bounded]?.queue ?? "Unavailable"}
                        </strong>
                      </div>
                      <div>
                        <span>COMPLETED TRIPS</span>
                        <strong>{row.metrics.completed_trips}</strong>
                      </div>
                    </div>
                    <p>
                      Actual paired seed {row.seed}. This map shows SUMO
                      vehicles, not camera trajectories.
                    </p>
                  </section>
                ))}
              </div>
              <section className="city-panel">
                <div className="city-toolbar">
                  <button
                    className="button"
                    onClick={() => setPlaying(!playing)}
                  >
                    {playing ? "Pause recorded replay" : "Play recorded replay"}
                  </button>
                  <span>
                    {frames[bounded]?.t ?? 0} / {candidate.duration} simulated
                    seconds · linked timelines · five-second recorded samples
                  </span>
                  <label>
                    Replay time
                    <input
                      aria-label="Network replay timeline"
                      type="range"
                      min={0}
                      max={Math.max(0, frames.length - 1)}
                      value={bounded}
                      onChange={(event) => {
                        setIndex(Number(event.target.value));
                        setPlaying(false);
                      }}
                    />
                  </label>
                </div>
                <label>
                  Inspect intersection
                  <select
                    aria-label="Inspect replay intersection"
                    value={inspected ?? ""}
                    onChange={(event) => setSignal(event.target.value)}
                  >
                    {Object.keys(frames[bounded]?.signals ?? {}).map((id) => (
                      <option key={id}>{id}</option>
                    ))}
                  </select>
                </label>
                <div className="calibration-detail-grid">
                  {[reference, candidate].map((row) => {
                    const state = row.trace[bounded]?.signals[inspected];
                    return (
                      <div key={row.policy}>
                        <h3>{POLICY[row.policy]}</h3>
                        <p>
                          Local queue: {state?.queue ?? "Unavailable"} · phase:{" "}
                          {state?.phase ?? "Unavailable"}
                        </p>
                        <p>
                          Decision:{" "}
                          {state?.reason.replaceAll("_", " ") ??
                            "No decision at this time"}
                        </p>
                        <code>{state?.state}</code>
                      </div>
                    );
                  })}
                </div>
                <p>
                  Selector family:{" "}
                  {decision?.family?.replaceAll("_", " ") ?? "Unavailable"}.
                  Observed inbound occupancy:{" "}
                  {decision?.inbound_occupancy_fraction == null
                    ? "Unavailable"
                    : `${number(decision.inbound_occupancy_fraction * 100)}%`}
                  . Only legal phases allowed by the independent safety gate can
                  execute.
                </p>
              </section>
            </>
          )}
          <section className="city-panel">
            <h2>Promotion decision & evidence limits</h2>
            <ul>
              {Object.entries(current.promotion_checks).map(([key, passed]) => (
                <li key={key}>
                  {key.replaceAll("_", " ")}: {passed ? "passed" : "failed"}
                </li>
              ))}
            </ul>
            <p>
              The portfolio is not promoted. Queue surrogate selection is
              retired: the previous learned model lost to persistence in all
              five cities.
            </p>
            <p>
              Hosted execution is disabled. Genuine recorded comparisons are
              available immediately; bounded new SUMO execution has been
              verified privately in the native backend.
            </p>
            <a
              href="https://github.com/youssef061204/ATLAS/tree/main/artifacts/cities/v5"
              target="_blank"
              rel="noreferrer"
            >
              Inspect source provenance, every seed and lossless evidence
            </a>
          </section>
        </>
      )}
    </Shell>
  );
}
