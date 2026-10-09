"use client";
import { useEffect, useState } from "react";
import { request } from "@/lib/api";
import { POLICY, type Experiments } from "@/lib/cities";
export function CityBenchmarks() {
  const [data, setData] = useState<Experiments | null>(null);
  useEffect(() => {
    let active = true;
    request<Experiments>("/api/operations/experiments")
      .then((d) => {
        if (active) setData(d);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  if (!data) return null;
  return (
    <section className="city-panel">
      <h2>ATLAS 2.0 · multi-city laboratory</h2>
      <p>{data.scope}</p>
      <div
        className="table-wrap"
        role="region"
        aria-label="City benchmark comparison"
        tabIndex={0}
      >
        <table aria-label="Exploratory city benchmark metrics">
          <thead>
            <tr>
              <th>City</th>
              <th>Controller</th>
              <th>Seeds</th>
              <th>Mean delay ± SD</th>
              <th>Mean 95% CI</th>
              <th>Decision p95</th>
            </tr>
          </thead>
          <tbody>
            {data.summaries.map((s) => (
              <tr key={s.city + s.policy}>
                <td>{s.city}</td>
                <td>{POLICY[s.policy] ?? s.policy}</td>
                <td>{s.seeds}</td>
                <td>
                  {s.mean_delay_s.toFixed(2)} ± {s.sd?.toFixed(2) ?? "—"} s
                </td>
                <td>
                  {s.ci95?.map((v) => v.toFixed(2)).join("–") ??
                    "Insufficient samples"}
                </td>
                <td>{s.decision_ms_p95.toFixed(3)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        Each controller was evaluated on 20 paired seeds per city. These short
        nominal episodes do not establish multiple-regime, calibrated municipal
        validation. Historical Cologne/UA-DETRAC/METR-LA results remain separate
        below.
      </p>
      {data.failures.length > 0 && (
        <details>
          <summary>Failed executions ({data.failures.length})</summary>
          {data.failures.map((f, i) => (
            <p key={i}>
              {f.city} / {f.policy}: {f.reason}
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
