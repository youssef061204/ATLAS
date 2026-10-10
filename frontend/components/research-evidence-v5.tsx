"use client";

import { useEffect, useState } from "react";

type ForecastRow = {
  city?: string;
  held_out_city?: string;
  selected_candidate: string;
  final: { mae_count: number; interval_seconds: number[] };
  persistence: { mae_count: number };
  mae_reduction_vs_persistence_pct: number;
  interval: {
    empirical_coverage: number;
    mean_width_count: number;
    mean_interval_score: number;
  };
};
type Geometry = {
  city: string;
  status: string;
  limitation?: string;
  reason?: string;
  source?: string;
  hourly_direction_rows?: number;
  matched_keys?: number[];
};
type Evidence = {
  forecast: { local: ForecastRow[]; zero_shot: ForecastRow[] };
  geometry: { cities: Geometry[] };
};

export function ResearchEvidenceV5({ city }: { city: string }) {
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    const get = async (name: string) => {
      const response = await fetch(`/demo/cities/v5/${name}.json`, {
        signal: abort.signal,
      });
      if (!response.ok) throw new Error("Research evidence unavailable");
      return response.json();
    };
    Promise.all([get("forecast-results"), get("geometry-investigation")])
      .then(([forecast, geometry]) => {
        if (!abort.signal.aborted) setData({ forecast, geometry });
      })
      .catch((e: unknown) => {
        if (!abort.signal.aborted)
          setError(e instanceof Error ? e.message : "Evidence unavailable");
      });
    return () => abort.abort();
  }, []);
  const geometry = data?.geometry.cities.find((row) => row.city === city);
  const rows = [
    {
      mode: "City-trained",
      value: data?.forecast.local.find((row) => row.city === city),
    },
    {
      mode: "Source-only zero-shot",
      value: data?.forecast.zero_shot.find((row) => row.held_out_city === city),
    },
  ];
  return (
    <section
      className="city-panel"
      aria-label="ATLAS 5 source and forecast investigation"
    >
      <h2>What changed in the research study?</h2>
      {error && <p role="alert">{error}</p>}
      {geometry && (
        <>
          <h3>Official source follow-up</h3>
          <p>
            {geometry.status.replaceAll("_", " ")}.{" "}
            {geometry.hourly_direction_rows != null &&
              `${geometry.hourly_direction_rows} actual hourly directional surveys acquired. `}
            {geometry.matched_keys &&
              `${geometry.matched_keys.length} current official street segments resolved. `}
            {geometry.limitation ?? geometry.reason}
          </p>
          {geometry.source && (
            <a href={geometry.source} target="_blank" rel="noreferrer">
              Inspect official source
            </a>
          )}
        </>
      )}
      {data && (
        <>
          <h3>Causal forecasting and strict cross-city transfer</h3>
          <p>
            Historical regression cohort, already evaluated in ATLAS 4.
            Zero-shot parameters and interval calibration use the other four
            cities only. Final outcomes did not select the model. These
            predictions are not promoted into signal control.
          </p>
          <div
            className="calibration-table-wrap"
            role="region"
            aria-label="Scroll forecast investigation"
            tabIndex={0}
          >
            <table aria-label="ATLAS 5 forecast regression results">
              <thead>
                <tr>
                  <th scope="col">Mode</th>
                  <th scope="col">Model / native horizon</th>
                  <th scope="col">MAE / persistence</th>
                  <th scope="col">MAE reduction</th>
                  <th scope="col">90% interval coverage</th>
                  <th scope="col">Width / interval score</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(
                  ({ mode, value }) =>
                    value && (
                      <tr key={mode}>
                        <th scope="row">{mode}</th>
                        <td>
                          {value.selected_candidate} /{" "}
                          {value.final.interval_seconds
                            .map((n) => `${n / 60} min`)
                            .join(", ")}
                        </td>
                        <td>
                          {value.final.mae_count.toFixed(2)} /{" "}
                          {value.persistence.mae_count.toFixed(2)} veh
                        </td>
                        <td
                          className={
                            value.mae_reduction_vs_persistence_pct < 0
                              ? "forecast-regression"
                              : ""
                          }
                        >
                          {value.mae_reduction_vs_persistence_pct.toFixed(2)}%
                          {value.mae_reduction_vs_persistence_pct < 0 &&
                            " · regressed"}
                        </td>
                        <td>
                          {(100 * value.interval.empirical_coverage).toFixed(1)}
                          %
                        </td>
                        <td>
                          {value.interval.mean_width_count.toFixed(2)} /{" "}
                          {value.interval.mean_interval_score.toFixed(2)} veh
                        </td>
                      </tr>
                    ),
                )}
              </tbody>
            </table>
          </div>
          <p>
            No verified directed sensor graph or contemporaneous calibrated
            camera/detector pair is available. Multimodal accuracy and physical
            queue error remain unmeasured. The confidence-aware fusion module
            rejects incompatible, stale, overlapping and unmapped measurements.
          </p>
        </>
      )}
    </section>
  );
}
