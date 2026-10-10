"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CITY_CHOICES, useCitySelection } from "@/lib/city-selection";
import { Shell } from "./shell";
import { ResearchEvidenceV5 } from "./research-evidence-v5";

type CityEvidence = {
  city: string;
  record_count: number;
  observation_dates: number;
  period: string[];
  source_years: string[];
  native_intervals_seconds: number[];
  license: { name: string; url: string };
  sources: string[];
  inputs: Record<string, string>;
  evidence_level: number;
  twin_status: string;
  verified_sensor_mappings: number;
  calibratable_scope: string;
  alternative_corridor_candidates: {
    site_id: string;
    name: string;
    candidate_bbox: number[] | null;
    status: string;
  }[];
  blockers: string[];
  limitations: string[];
  split_dates: Record<string, string[]>;
  count_demand_regression?: {
    final: {
      rows: number;
      coverage_fraction: number;
      count_mae: number;
      count_rmse: number;
      flow_mae_vph: number;
      count_normalized_mae: number | null;
      geh_below_5_fraction: number;
    };
    mae_95ci: { interval: number[] | null; dates: number; reason?: string };
    final_is_new_unseen_cohort: boolean;
    scope: string;
  };
};
type Evidence = {
  generated_at: string;
  independently_validated_twins: number;
  cities: CityEvidence[];
  protocol_sha256: string;
};
type Point = {
  observed_at: string;
  site_id: string;
  direction: string | null;
  observed_count: number;
  estimated_demand_count: number | null;
  simulated_count: null;
  interval_seconds: number;
};

const fmt = (value: number | null | undefined, suffix = "") =>
  value == null ? "Unavailable" : `${value.toFixed(1)}${suffix}`;

export function CalibrationDashboard() {
  const [city] = useCitySelection();
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/demo/cities/v5/calibration-readiness.json", {
      signal: abort.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("Calibration evidence unavailable");
        return response.json() as Promise<Evidence>;
      })
      .then(setEvidence)
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setError(e instanceof Error ? e.message : "Evidence unavailable");
      });
    return () => abort.abort();
  }, [revision]);
  const selected = evidence?.cities.find((row) => row.city === city);
  const name = CITY_CHOICES.find((choice) => choice.id === city)?.name ?? city;
  const metrics = selected?.count_demand_regression?.final;
  const interval = selected?.count_demand_regression?.mae_95ci;
  return (
    <Shell
      title="Twin validation"
      eyebrow="REAL OBSERVATIONS → EVIDENCE → DECISIONS"
    >
      <div className="calibration-hero city-panel">
        <span className="city-status">EVIDENCE LEVEL 1 · EXPLORATORY</span>
        <h2>How closely does {name}&apos;s twin match reality?</h2>
        <p>
          Start with the evidence. Official historical counts support demand
          estimation. Independently measured simulation-state accuracy is still
          unavailable.
        </p>
        <div
          className="calibration-journey"
          aria-label="City investigation workflow"
        >
          <Link href={`/cities?city=${city}`}>1. Observations</Link>
          <span aria-current="step">2. Validate the twin</span>
          <Link href={`/twin?city=${city}`}>3. Inspect corridor</Link>
          <Link href={`/studio?city=${city}&cohort=atlas-5`}>
            4. Compare control
          </Link>
          <Link href={`/pilot?city=${city}&cohort=atlas-5`}>
            5. Pilot assessment
          </Link>
        </div>
      </div>
      {error && !evidence && (
        <div className="city-panel" role="alert">
          <p>{error}. Recorded city experiments remain available.</p>
          <button
            className="button"
            onClick={() => {
              setError("");
              setRevision(revision + 1);
            }}
          >
            Retry evidence
          </button>
        </div>
      )}
      {!evidence && !error && (
        <div
          className="city-panel evidence-reserved"
          role="status"
          aria-busy="true"
        >
          Loading published calibration evidence…
        </div>
      )}
      {evidence && (
        <>
          <section
            className="city-panel calibration-matrix"
            aria-label="Five-city validation matrix"
          >
            <div className="section-heading">
              <h2>Five-city evidence matrix</h2>
              <span>
                {evidence.independently_validated_twins} independently validated
                twins
              </span>
            </div>
            <div
              className="calibration-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Scroll calibration readiness"
            >
              <table>
                <caption>
                  Historical count-demand reconstruction. These errors do not
                  measure simulator dynamics.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">City</th>
                    <th scope="col">Count bins</th>
                    <th scope="col">Demand MAE</th>
                    <th scope="col">Estimate coverage</th>
                    <th scope="col">Twin status</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.cities.map((row) => (
                    <tr
                      key={row.city}
                      className={city === row.city ? "selected" : ""}
                    >
                      <th scope="row">
                        <Link href={`/calibration?city=${row.city}`}>
                          {
                            CITY_CHOICES.find(
                              (choice) => choice.id === row.city,
                            )?.name
                          }
                        </Link>
                      </th>
                      <td>{row.record_count.toLocaleString()}</td>
                      <td>
                        {fmt(row.count_demand_regression?.final.count_mae)}{" "}
                        <small>veh / native bin</small>
                      </td>
                      <td>
                        {fmt(
                          row.count_demand_regression
                            ? row.count_demand_regression.final
                                .coverage_fraction * 100
                            : null,
                          "%",
                        )}
                      </td>
                      <td>Exploratory · unvalidated states</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {selected && (
            <>
              <section
                className="city-panel"
                aria-label={`${name} calibration quality`}
              >
                <div className="section-heading">
                  <h2>{name}: observed counts & estimated demand</h2>
                  <span>Previously published historical cohort</span>
                </div>
                <div className="calibration-stat-grid">
                  <div>
                    <span>Count MAE</span>
                    <strong>{fmt(metrics?.count_mae)}</strong>
                    <small>vehicles per native interval</small>
                  </div>
                  <div>
                    <span>Count RMSE</span>
                    <strong>{fmt(metrics?.count_rmse)}</strong>
                    <small>vehicles per native interval</small>
                  </div>
                  <div>
                    <span>Flow MAE</span>
                    <strong>{fmt(metrics?.flow_mae_vph)}</strong>
                    <small>equivalent vehicles / hour</small>
                  </div>
                  <div>
                    <span>Estimate coverage</span>
                    <strong>
                      {fmt(
                        metrics ? metrics.coverage_fraction * 100 : null,
                        "%",
                      )}
                    </strong>
                    <small>Unknown channels receive no estimate</small>
                  </div>
                </div>
                <p className="calibration-note">
                  Calibration, validation and final rows are separated by whole
                  observation dates. ATLAS 4 already evaluated this source
                  archive, so this is historical regression evidence. No newly
                  unseen ATLAS 5 cohort is claimed.
                </p>
                <DemandSeries key={city} city={city} />
                <p>
                  Count MAE 95% date-cluster interval:{" "}
                  {interval?.interval
                    ? `${fmt(interval.interval[0])}–${fmt(interval.interval[1])} vehicles`
                    : "Unavailable: too few independent dates"}
                  . Flow GEH below 5:{" "}
                  {fmt(
                    metrics ? metrics.geh_below_5_fraction * 100 : null,
                    "%",
                  )}
                  .
                </p>
                <div className="calibration-missing">
                  <strong>Simulation-state comparisons pending</strong>
                  <span>Speed · travel time · physical queue · occupancy</span>
                  <p>
                    Independent observations and verified historical sensor
                    mappings are needed. These values stay unavailable.
                  </p>
                </div>
              </section>
              <ResearchEvidenceV5 city={city} />
              <div className="calibration-detail-grid">
                <section className="city-panel">
                  <h2>What the evidence supports</h2>
                  <dl className="calibration-inputs">
                    {Object.entries(selected.inputs).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key.replaceAll("_", " ")}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                </section>
                <section className="city-panel">
                  <h2>What is needed to validate this twin</h2>
                  <ul>
                    {selected.blockers.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                  <h3>Alternative corridors under investigation</h3>
                  <ul>
                    {selected.alternative_corridor_candidates.map((row) => (
                      <li key={row.site_id}>
                        <strong>{row.name}</strong>
                        <small>{row.status}</small>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
              <section className="city-panel calibration-provenance">
                <h2>Observation provenance</h2>
                <p>
                  {selected.period.join(" to ")} · {selected.observation_dates}{" "}
                  observation dates · native bins{" "}
                  {selected.native_intervals_seconds
                    .map((value) => `${value / 60} min`)
                    .join(", ")}
                  .
                </p>
                <p>
                  Source years: {selected.source_years.join(", ")}. Different
                  years are historical studies, not simultaneous measurements.
                </p>
                <a href={selected.license.url} target="_blank" rel="noreferrer">
                  {selected.license.name}
                </a>
                <details>
                  <summary>
                    Sources, chronological partitions & limitations
                  </summary>
                  <ul>
                    {selected.sources.map((source) => (
                      <li key={source}>
                        <a href={source} target="_blank" rel="noreferrer">
                          Official source
                        </a>
                      </li>
                    ))}
                  </ul>
                  {Object.entries(selected.split_dates).map(
                    ([partition, dates]) => (
                      <p key={partition}>
                        <strong>{partition}</strong>: {dates.join(", ")}
                      </p>
                    ),
                  )}
                  <ul>
                    {selected.limitations.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                  <p>
                    Protocol SHA-256: <code>{evidence.protocol_sha256}</code>
                  </p>
                </details>
              </section>
            </>
          )}
        </>
      )}
    </Shell>
  );
}

function DemandSeries({ city }: { city: string }) {
  const [series, setSeries] = useState<Point[]>([]);
  const [study, setStudy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    fetch(`/demo/cities/v5/demand-${city}.json`, { signal: abort.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Demand series unavailable");
        return response.json() as Promise<Point[]>;
      })
      .then(setSeries)
      .catch(() => {
        if (!abort.signal.aborted)
          setError("The measured demand series is unavailable.");
      });
    return () => abort.abort();
  }, [city]);
  const key = (row: Point) =>
    `${row.site_id}|${row.direction ?? "all"}|${row.observed_at.slice(0, 10)}`;
  const studies = [...new Set(series.map(key))];
  const selection = studies.includes(study) ? study : studies[0];
  const rows = series
    .filter((row) => key(row) === selection)
    .toSorted((a, b) => a.observed_at.localeCompare(b.observed_at));
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => [
      row.observed_count,
      row.estimated_demand_count ?? 0,
    ]),
  );
  const x = (i: number) => 42 + (i / Math.max(1, rows.length - 1)) * 616;
  const y = (value: number) => 194 - (value / maximum) * 150;
  const observed = rows
    .map((row, i) => `${x(i)},${y(row.observed_count)}`)
    .join(" ");
  return (
    <div className="calibration-series">
      <label>
        Inspect observed site / direction / study date
        <select
          value={selection ?? ""}
          onChange={(event) => setStudy(event.target.value)}
        >
          {studies.map((value) => (
            <option key={value}>{value.replaceAll("|", " · ")}</option>
          ))}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="calibration-legend">
        <span>● Observed count</span>
        <span>◆ Estimated demand</span>
      </div>
      <svg
        viewBox="0 0 700 245"
        role="img"
        aria-label="Observed traffic counts and estimated historical demand; no simulated-state series available"
      >
        <line x1="42" x2="660" y1="194" y2="194" stroke="#5e7983" />
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line
              x1="42"
              x2="660"
              y1={y(maximum * fraction)}
              y2={y(maximum * fraction)}
              stroke="#354b54"
            />
            <text
              x="3"
              y={y(maximum * fraction) + 4}
              fill="#c2d5d9"
              fontSize="11"
            >
              {Math.round(maximum * fraction)}
            </text>
          </g>
        ))}
        <polyline
          points={observed}
          fill="none"
          stroke="#a8eddb"
          strokeWidth="2.5"
        />
        {rows.map((row, i) =>
          row.estimated_demand_count == null ? null : (
            <path
              key={row.observed_at}
              d={`M ${x(i)} ${y(row.estimated_demand_count) - 3} l 3 3 l -3 3 l -3 -3 Z`}
              fill="#ffca8c"
            >
              <title>
                {row.observed_at.slice(11, 16)}: demand{" "}
                {row.estimated_demand_count.toFixed(1)}, observed{" "}
                {row.observed_count}
              </title>
            </path>
          ),
        )}
        <text x="42" y="218" fill="#c2d5d9" fontSize="12">
          {rows[0]?.observed_at.slice(11, 16)}
        </text>
        <text x="622" y="218" fill="#c2d5d9" fontSize="12">
          {rows.at(-1)?.observed_at.slice(11, 16)}
        </text>
        <text x="42" y="238" fill="#c2d5d9" fontSize="11">
          Vehicles / {rows[0] ? rows[0].interval_seconds / 60 : "native"} minute
          bin · source timestamp basis retained
        </text>
      </svg>
      <details>
        <summary>View exact measurement values</summary>
        <div
          className="calibration-table-wrap"
          tabIndex={0}
          role="region"
          aria-label="Scroll observed measurement values"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Source time</th>
                <th scope="col">Observed</th>
                <th scope="col">Estimated demand</th>
                <th scope="col">Simulated</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.observed_at}>
                  <th scope="row">{row.observed_at.slice(11, 16)}</th>
                  <td>{row.observed_count}</td>
                  <td>{fmt(row.estimated_demand_count)}</td>
                  <td>Unavailable</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
