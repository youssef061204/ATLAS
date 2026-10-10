"use client";
import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { POLICY, type Experiments, type Run } from "@/lib/cities";
import { Shell } from "./shell";
import { readSelectedCity, selectCity } from "@/lib/city-selection";

export function PilotStudio() {
  const [data, setData] = useState<Experiments | null>(null);
  const [city, setCity] = useState("toronto");
  const [vehicles, setVehicles] = useState(1000);
  const [occupancy, setOccupancy] = useState(1.2);
  const [value, setValue] = useState(20);
  const [days, setDays] = useState(250);
  const [cost, setCost] = useState(100);
  const [error, setError] = useState("");
  const [baseline, setBaseline] = useState("fixed");
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [cohort, setCohort] = useState("atlas-2");
  const [scenario, setScenario] = useState("nominal");
  useEffect(() => {
    let active = true;
    const parameters = new URL(window.location.href).searchParams;
    const id = parameters.get("experiment");
    const requestedCohort = ["atlas-4", "atlas-5"].includes(
      parameters.get("cohort") ?? "",
    )
      ? parameters.get("cohort")!
      : "atlas-2";
    const requestedScenario = [
      "low",
      "nominal",
      "high",
      "incident",
      "outage",
      "shift",
    ].includes(parameters.get("case") ?? "")
      ? parameters.get("case")!
      : "nominal";
    const result = id
      ? request<{ runs: Run[]; city: string; id: string }>(
          `/api/operations/intelligence/${encodeURIComponent(id)}`,
        )
      : requestedCohort === "atlas-5"
        ? fetch(`/demo/cities/v5/pilot-${requestedScenario}.json`).then(
            (response) => {
              if (!response.ok)
                throw new Error("Paired ATLAS 5 evidence unavailable");
              return response.json() as Promise<Experiments>;
            },
          )
        : request<Experiments>(
            requestedCohort === "atlas-4"
              ? "/api/operations/control-v4/assessment"
              : "/api/operations/experiments",
          );
    result
      .then((d) => {
        if ("id" in d) {
          const pair = d;
          if (!active) return;
          setData({
            scope:
              "One actual observation-conditioned pair; economic inputs are unvalidated assumptions",
            failures: [],
            paired: [],
            runs: pair.runs,
            summaries: pair.runs.map((r) => ({
              city: r.city,
              policy: r.policy,
              seeds: 1,
              mean_delay_s: r.metrics.mean_delay_s,
              sd: null,
              ci95: null,
              decision_ms_p95: r.metrics.decision_ms_p95,
            })),
          });
          setCity(pair.city);
          setBaseline(pair.runs[0].policy);
          setExperimentId(pair.id);
        } else if (active) {
          setData(d);
          setCohort(requestedCohort);
          setScenario(requestedScenario);
          const selected = readSelectedCity();
          if (selected && d.runs.some((r) => r.city === selected))
            setCity(selected);
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  const fixed = data?.summaries.find(
    (s) => s.city === city && s.policy === baseline,
  );
  const candidate = data?.summaries.find(
    (s) =>
      s.city === city &&
      s.policy ===
        (cohort === "atlas-5"
          ? "portfolio_v5"
          : cohort === "atlas-4"
            ? "network_mpc"
            : "risk_mpc"),
  );
  const delta =
    fixed && candidate ? fixed.mean_delay_s - candidate.mean_delay_s : null;
  const hours =
    delta === null ? null : (delta * vehicles * occupancy * days) / 3600;
  const annual = hours === null ? null : hours * value;
  const paired = data?.paired?.find(
    (p) => p.city === city && p.baseline === baseline,
  );
  const projectedRange = paired?.paired_difference_ci95.map(
    (difference) => (difference * vehicles * occupancy * days * value) / 3600,
  );
  const report = {
    city,
    evidence_cohort: cohort,
    scenario_case: scenario,
    production_promoted: false,
    calibration_status:
      "exploratory; independently measured simulation dynamics unavailable",
    experiment_id: experimentId,
    scope:
      "Uncalibrated SUMO experiment; economic quantities are user-assumption projections, not verified field savings",
    baseline: fixed,
    candidate,
    delay_difference_s: delta,
    paired_delay_ci95_s: paired?.paired_difference_ci95 ?? null,
    projected_value_ci95_from_simulation_seed_variation: projectedRange ?? null,
    uncertainty_qualification:
      "Seed variation only; field calibration and economic uncertainty are not quantified. Single-run experiments have no estimated interval.",
    simulation_inputs: data?.runs
      .filter((r) => r.city === city)
      .map((r) => ({
        seed: r.seed,
        policy: r.policy,
        network_sha256: r.network_sha256,
        routes_sha256: r.routes_sha256,
        scenario: r.scenario,
        duration: r.duration,
      })),
    assumptions: {
      vehicles_per_day: vehicles,
      occupancy,
      value_per_person_hour: value,
      days_per_year: days,
      compute_monthly: cost,
    },
    projected_person_hours_per_year: hours,
    projected_value_per_year: annual,
    projected_net_before_deployment:
      annual === null ? null : annual - 12 * cost,
    requirements: [
      "Independent counts and heldout validation",
      "Agency timing, conflict and pedestrian survey",
      "Camera feed permissions",
      "Operator-approved shadow operation",
      "Hardware certification not implemented",
    ],
    field_validated: false,
  };
  function exportReport() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `atlas-${city}-pilot-assessment.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <Shell
      title="Municipal pilot studio"
      eyebrow="EVIDENCE / ASSUMPTIONS / HUMAN OVERSIGHT"
    >
      <p className="city-notice">
        Plan a supervised advisory pilot. The evidence is exploratory
        simulation. Annual traffic volume, occupancy and economic assumptions
        below are user inputs; their projections are not measured municipal
        benefits.
      </p>
      {error && <p role="alert">{error}</p>}
      {!experimentId && (
        <label className="cohort-selector">
          Assessment evidence
          <select
            aria-label="Pilot evidence cohort"
            value={cohort}
            onChange={(event) => {
              const url = new URL(window.location.href);
              url.searchParams.set("cohort", event.target.value);
              url.searchParams.set("city", city);
              window.location.assign(url.toString());
            }}
          >
            <option value="atlas-2">Retained ATLAS 2 exploratory study</option>
            <option value="atlas-4">ATLAS 4 nominal held-out study</option>
            <option value="atlas-5">
              ATLAS 5 robustness study · experimental, not promoted
            </option>
          </select>
        </label>
      )}
      <div className="city-columns">
        <section className="city-panel">
          <h2>Pilot assumptions</h2>
          <label>
            City{" "}
            <select
              aria-label="Pilot city"
              value={city}
              onChange={(e) => {
                selectCity(e.target.value);
                setCity(e.target.value);
              }}
            >
              {[...new Set(data?.runs.map((r) => r.city))].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          {[
            ["Vehicles per day", vehicles, setVehicles, 1, 10000000],
            ["Persons per vehicle", occupancy, setOccupancy, 1, 20],
            ["Value per person-hour", value, setValue, 0, 500],
            ["Operating days per year", days, setDays, 1, 366],
            ["Compute cost per month", cost, setCost, 0, 1000000],
          ].map(([label, v, set, min, max]) => (
            <label className="pilot-field" key={String(label)}>
              {String(label)}
              <input
                aria-label={String(label)}
                type="number"
                min={Number(min)}
                max={Number(max)}
                step="any"
                value={Number(v)}
                onChange={(e) =>
                  (set as (v: number) => void)(
                    Math.min(
                      Number(max),
                      Math.max(Number(min), Number(e.target.value)),
                    ),
                  )
                }
              />
            </label>
          ))}
          <p>
            Currency is your chosen unit. Cost assumptions exclude labor, field
            equipment, integration, procurement and maintenance.
          </p>
        </section>
        <section className="city-panel">
          <h2>Evidence-based assessment</h2>
          {delta !== null ? (
            <>
              <p>
                {POLICY[baseline]}: {fixed!.mean_delay_s.toFixed(2)} s ·
                prototype: {candidate!.mean_delay_s.toFixed(2)} s ·{" "}
                {candidate!.seeds} paired seeds
              </p>
              <div className="city-metrics">
                <div>
                  <span>SIMULATED DELAY DIFFERENCE</span>
                  <strong>{delta.toFixed(2)} s</strong>
                </div>
                <div>
                  <span>PROJECTED PERSON-HOURS / YEAR</span>
                  <strong>{hours!.toFixed(0)}</strong>
                </div>
                <div>
                  <span>PROJECTED VALUE / YEAR</span>
                  <strong>{annual!.toFixed(0)}</strong>
                </div>
              </div>
              <p>
                {projectedRange
                  ? `Projected annual value range from paired simulation seeds: ${projectedRange[0].toFixed(0)} to ${projectedRange[1].toFixed(0)} (95% bootstrap interval). This excludes field calibration and economic uncertainty.`
                  : "This single paired run has no estimated uncertainty interval. Field calibration and economic uncertainty remain unquantified."}
              </p>
              <p>
                Positive delay difference means lower prototype delay. Negative
                benefits remain negative; the calculator never clamps
                regressions into savings.
              </p>
              <button className="button" onClick={exportReport}>
                Export pilot assessment
              </button>
              <button className="button" onClick={() => window.print()}>
                Print report
              </button>
            </>
          ) : (
            <p>Matched completed evidence is required.</p>
          )}
          <h3>Before a municipal pilot</h3>
          <ul>
            {report.requirements.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p>
            Read-only public mode. Approvals, rejections and rollback can be
            logged through the authenticated local advisory API; none sends
            commands to real signal hardware.
          </p>
        </section>
      </div>
    </Shell>
  );
}
