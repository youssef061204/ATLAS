"use client";

import { useEffect, useState } from "react";
import { request } from "@/lib/api";

type Metrics = {
  examples: number;
  mae_count_per_native_interval: number;
  rmse_count_per_native_interval: number;
  interval_seconds: number[];
};
type Preview = {
  site_id: string;
  time: string;
  interval_seconds: number;
  actual: number;
  predicted: number;
  persistence: number;
  lower: number;
  upper: number;
  observed_neighbors: number;
};
type Evidence = {
  city: string;
  historical_data: {
    records: number;
    sites: number;
    period_start: string;
    period_end: string;
    status: string;
    license: { name: string; url: string };
    limitations: string[];
  }[];
  forecast: null | {
    status: string;
    validation_selected: string;
    models: {
      name: string;
      validation: Metrics;
      test: Metrics;
      parameters?: number;
    }[];
    partition_examples: { train: number; validation: number; test: number };
    split: {
      split_dates: { train: string[]; validation: string[]; test: string[] };
      graph: string;
      neighbor_coverage_fraction: number;
    };
    uncertainty: {
      nominal_coverage: number;
      test_coverage: number;
      scope: string;
    };
    preview: Preview[];
    preview_selection: string;
  };
  transfer: null | {
    status: string;
    trained_cities: string[];
    target_city_fit_examples: number;
    test: Metrics;
    persistence: Metrics;
    promoted: boolean;
  };
  validation: { field_calibrated: boolean; limitations: string[] };
};
const NAMES: Record<string, string> = {
  persistence: "Last observed count",
  training_calendar_median: "Training calendar median",
  histogram_gradient_boosting: "Gradient boosting",
  temporal_mlp: "Temporal MLP",
  geographic_message_network: "Geographic message network",
};

export function CityEvidenceV4({ city }: { city: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="city-evidence-entry"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Inspect historical city data & forecast validation</summary>
      {open && <CityEvidenceContent key={city} city={city} />}
    </details>
  );
}

function CityEvidenceContent({ city }: { city: string }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState("");
  useEffect(() => {
    let active = true;
    request<Evidence>(
      `/api/operations/cities/${encodeURIComponent(city)}/evidence-v4`,
    )
      .then((data) => {
        if (active) {
          setEvidence(data);
          setError("");
          setSelection("");
        }
      })
      .catch(() => {
        if (active)
          setError(
            "Historical city evidence is currently unavailable. Camera observations and retained simulations remain separately inspectable.",
          );
      });
    return () => {
      active = false;
    };
  }, [city]);
  const current = evidence?.city === city ? evidence : null;
  const forecast = current?.forecast;
  const studies = [
    ...new Set(
      forecast?.preview.map(
        (row) => `${row.site_id}|${row.time.split("T")[0]}`,
      ),
    ),
  ];
  const study = studies.includes(selection) ? selection : studies[0];
  const rows =
    forecast?.preview
      .filter((row) => `${row.site_id}|${row.time.split("T")[0]}` === study)
      .toSorted((a, b) => a.time.localeCompare(b.time)) ?? [];
  const max = Math.max(
    1,
    ...rows.flatMap((row) => [row.actual, row.predicted, row.persistence]),
  );
  const points = (key: "actual" | "predicted" | "persistence") =>
    rows
      .map(
        (row, index) =>
          `${40 + (index / Math.max(1, rows.length - 1)) * 620},${190 - (row[key] / max) * 160}`,
      )
      .join(" ");
  const selected = forecast?.models.find(
    (model) => model.name === forecast.validation_selected,
  );
  const persistence = forecast?.models.find(
    (model) => model.name === "persistence",
  );
  const change =
    selected && persistence
      ? (100 *
          (persistence.test.mae_count_per_native_interval -
            selected.test.mae_count_per_native_interval)) /
        persistence.test.mae_count_per_native_interval
      : null;
  return (
    <section
      className="city-panel city-evidence-v4"
      aria-label="Historical city evidence"
    >
      <div className="eyebrow">
        OFFICIAL HISTORICAL DATA / HELD-OUT CITY FORECASTS
      </div>
      <h2>What this city’s evidence supports</h2>
      {error ? (
        <p role="status">{error}</p>
      ) : !current ? (
        <p role="status">Loading historical source evidence…</p>
      ) : (
        <>
          <p>
            These observations have their own dates and locations. They are kept
            separate from the current camera snapshot and exploratory SUMO
            demand.
          </p>
          {current.historical_data.map((source, index) => (
            <div key={index}>
              <div className="city-metrics">
                <div>
                  <span>ACTUAL COUNT RECORDS</span>
                  <strong>{source.records.toLocaleString()}</strong>
                </div>
                <div>
                  <span>OBSERVED SITES</span>
                  <strong>{source.sites}</strong>
                </div>
                <div>
                  <span>FIELD-CALIBRATED TWIN</span>
                  <strong>
                    {current.validation.field_calibrated
                      ? "Validated"
                      : "Not established"}
                  </strong>
                </div>
              </div>
              <p>
                {source.period_start} → {source.period_end} · missing periods
                remain absent.{" "}
                <a href={source.license.url} target="_blank" rel="noreferrer">
                  {source.license.name} ↗
                </a>
              </p>
            </div>
          ))}
          {forecast?.status === "evaluated" ? (
            <>
              <h3>Forecast the next observed count interval</h3>
              <p>
                Forecast errors use vehicles per native observation interval,
                not mph or physical queue length. Training, validation and final
                dates are separated; the candidate was selected on validation
                and is not automatically promoted.
              </p>
              <div
                className="table-wrap"
                role="region"
                aria-label="City forecasting comparison scroll area"
                tabIndex={0}
              >
                <table aria-label="City forecasting comparison">
                  <thead>
                    <tr>
                      <th scope="col">Method</th>
                      <th scope="col">Validation MAE</th>
                      <th scope="col">Final MAE</th>
                      <th scope="col">Native interval</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.models.map((model) => (
                      <tr key={model.name}>
                        <th scope="row">
                          {NAMES[model.name] ?? model.name}
                          {model.name === forecast.validation_selected && (
                            <small> · validation-selected</small>
                          )}
                        </th>
                        <td>
                          {model.validation.mae_count_per_native_interval.toFixed(
                            2,
                          )}
                        </td>
                        <td>
                          {model.test.mae_count_per_native_interval.toFixed(2)}
                        </td>
                        <td>
                          {model.test.interval_seconds
                            .map((seconds) => `${seconds / 60} min`)
                            .join(" / ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p
                className={
                  change !== null && change < 0
                    ? "forecast-regression"
                    : "forecast-finding"
                }
              >
                {change === null
                  ? "No matched comparison available."
                  : change < 0
                    ? `The validation-selected candidate regresses ${Math.abs(change).toFixed(2)}% against persistence on the final holdout. This regression remains visible.`
                    : `The validation-selected candidate reduces final MAE by ${change.toFixed(2)}% against persistence in this historical holdout.`}
              </p>
              <p>
                {forecast.partition_examples.test.toLocaleString()} final
                examples across {forecast.split.split_dates.test.length}{" "}
                observation dates. Nominal interval coverage{" "}
                {(forecast.uncertainty.nominal_coverage * 100).toFixed(0)}%;
                measured final coverage{" "}
                {(forecast.uncertainty.test_coverage * 100).toFixed(1)}%.{" "}
                {forecast.uncertainty.scope}.
              </p>
              {rows.length > 0 && (
                <>
                  <label className="historical-preview-label">
                    Historical preview site / day
                    <select
                      aria-label="City forecast preview study"
                      value={study}
                      onChange={(event) => setSelection(event.target.value)}
                    >
                      {studies.map((item) => (
                        <option key={item} value={item}>
                          {item.replace("|", " · ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <figure className="historical-chart">
                    <svg
                      viewBox="0 0 700 220"
                      role="img"
                      aria-label="Actual historical counts, validation-selected forecast and persistence"
                    >
                      <line
                        x1="40"
                        y1="190"
                        x2="660"
                        y2="190"
                        stroke="#688089"
                      />
                      <text x="5" y="35" fill="#bfccd3" fontSize="11">
                        {max.toFixed(0)}
                      </text>
                      <text x="15" y="190" fill="#bfccd3" fontSize="11">
                        0
                      </text>
                      <polyline
                        points={points("actual")}
                        fill="none"
                        stroke="#b9e4c8"
                        strokeWidth="2.5"
                      />
                      <polyline
                        points={points("predicted")}
                        fill="none"
                        stroke="#b8c7f4"
                        strokeWidth="2"
                      />
                      <polyline
                        points={points("persistence")}
                        fill="none"
                        stroke="#e7bc83"
                        strokeWidth="1.5"
                        strokeDasharray="5 4"
                      />
                    </svg>
                    <figcaption>
                      Actual counts (green) · selected forecast (blue) ·
                      persistence (amber). {rows[0].time} → {rows.at(-1)!.time}.
                      Source-local timestamps are retained; the preview is
                      historical. {forecast.preview_selection}.
                    </figcaption>
                  </figure>
                  <details>
                    <summary>Inspect the actual dated forecast values</summary>
                    <div
                      className="table-wrap"
                      role="region"
                      aria-label="City historical preview scroll area"
                      tabIndex={0}
                    >
                      <table aria-label="City historical forecast values">
                        <thead>
                          <tr>
                            <th scope="col">Source-local time</th>
                            <th scope="col">Actual</th>
                            <th scope="col">Forecast</th>
                            <th scope="col">Persistence</th>
                            <th scope="col">Interval</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, index) => (
                            <tr key={index}>
                              <th scope="row">{row.time}</th>
                              <td>{row.actual.toFixed(1)}</td>
                              <td>{row.predicted.toFixed(1)}</td>
                              <td>{row.persistence.toFixed(1)}</td>
                              <td>
                                {row.lower.toFixed(1)}–{row.upper.toFixed(1)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </>
              )}
              {current.transfer && (
                <details>
                  <summary>Leave-one-city-out generalization</summary>
                  <p>
                    Trained on {current.transfer.trained_cities.join(", ")};{" "}
                    {current.transfer.target_city_fit_examples} target-city fit
                    examples. Zero-shot final MAE{" "}
                    {current.transfer.test.mae_count_per_native_interval.toFixed(
                      2,
                    )}{" "}
                    against persistence{" "}
                    {current.transfer.persistence.mae_count_per_native_interval.toFixed(
                      2,
                    )}{" "}
                    vehicles per native interval. This candidate is{" "}
                    {current.transfer.promoted ? "promoted" : "not promoted"}.
                  </p>
                </details>
              )}
            </>
          ) : (
            <p>
              No chronological forecasting evaluation is available for this
              city.
            </p>
          )}
          <details>
            <summary>Source validity and remaining pilot requirements</summary>
            <ul>
              {current.validation.limitations.map((limitation, index) => (
                <li key={index}>{limitation}</li>
              ))}
            </ul>
            {forecast && (
              <p>
                Graph construction: {forecast.split.graph}. Concurrent-neighbor
                coverage{" "}
                {(100 * forecast.split.neighbor_coverage_fraction).toFixed(1)}%.
                This is not a surveyed turning-flow graph.
              </p>
            )}
          </details>
        </>
      )}
    </section>
  );
}
