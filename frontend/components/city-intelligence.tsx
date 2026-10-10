"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { request } from "@/lib/api";
import type { CityReport, Network, TrafficContext } from "@/lib/cities";
import { Shell } from "./shell";
import { CityMap } from "./city-map";
import { useCitySelection } from "@/lib/city-selection";
import { CityEvidenceV4 } from "./city-evidence-v4";
import { EvidenceLoading } from "./evidence-loading";
import { CITY_CHOICES } from "@/lib/city-selection";

export function CityIntelligence() {
  const [reports, setReports] = useState<CityReport[]>([]);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [selected, setSelected] = useCitySelection();
  const [cameraId, setCameraId] = useState<string | null>(null);
  const [geometry, setGeometry] = useState(false);
  const [error, setError] = useState("");
  const [traffic, setTraffic] = useState<TrafficContext | null>(null);
  const [eventId, setEventId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [preferredCameras, setPreferredCameras] = useState<
    Record<string, string>
  >({});
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      request<{ cities: CityReport[] }>("/api/operations/cities"),
      request<{ networks: Network[] }>("/api/operations/networks"),
      request<TrafficContext>("/api/operations/traffic-context"),
      request<{
        city: string;
        observation: CityReport["observations"][number];
      }>("/api/operations/intelligence/context"),
      request<{
        records: {
          city: string;
          attempts: {
            camera_id: string;
            context?: { observation: CityReport["observations"][number] };
          }[];
        }[];
      }>("/api/operations/intelligence/smoke-v4"),
    ])
      .then(
        ([
          catalogResult,
          networkResult,
          trafficResult,
          observationResult,
          smokeResult,
        ]) => {
          if (active) {
            if (catalogResult.status !== "fulfilled") {
              setError(
                "Official source records could not be loaded. Retry this page when the service is available.",
              );
              return;
            }
            const c = catalogResult.value;
            const observations = [
              ...(observationResult.status === "fulfilled"
                ? [
                    {
                      city: observationResult.value.city,
                      observation: observationResult.value.observation,
                    },
                  ]
                : []),
              ...(smokeResult.status === "fulfilled"
                ? smokeResult.value.records.flatMap((record) =>
                    record.attempts
                      .filter((attempt) => attempt.context)
                      .map((attempt) => ({
                        city: record.city,
                        observation: attempt.context!.observation,
                      })),
                  )
                : []),
            ];
            setReports(
              c.cities.map((report) => {
                const additional = observations
                  .filter((item) => item.city === report.city)
                  .map((item) => item.observation);
                return {
                  ...report,
                  observations: [
                    ...report.observations.filter(
                      (old) =>
                        !additional.some(
                          (item) => item.camera_id === old.camera_id,
                        ),
                    ),
                    ...additional,
                  ],
                  image_checks: [
                    ...report.image_checks.filter(
                      (old) =>
                        !additional.some(
                          (item) => item.camera_id === old.camera_id,
                        ),
                    ),
                    ...additional.map((item) => ({
                      camera_id: item.camera_id,
                      status: "accessible",
                    })),
                  ],
                };
              }),
            );
            if (networkResult.status === "fulfilled")
              setNetworks(networkResult.value.networks);
            if (trafficResult.status === "fulfilled")
              setTraffic(trafficResult.value);
            if (smokeResult.status === "fulfilled")
              setPreferredCameras(
                Object.fromEntries(
                  smokeResult.value.records.map((record) => [
                    record.city,
                    record.attempts.find((attempt) => attempt.context)
                      ?.camera_id ?? "",
                  ]),
                ),
              );
            setCameraId(
              new URL(window.location.href).searchParams.get("camera"),
            );
          }
        },
      )
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  const city = reports.find((r) => r.city === selected);
  const filtered = useMemo(
    () =>
      city?.cameras.filter((c) =>
        `${c.name} ${c.id}`.toLowerCase().includes(search.toLowerCase()),
      ) ?? [],
    [city, search],
  );
  const mapCity = useMemo(
    () => (city ? { ...city, cameras: filtered } : undefined),
    [city, filtered],
  );
  const camera =
    filtered.find((c) => c.id === cameraId) ??
    filtered.find((c) => c.id === preferredCameras[selected]) ??
    filtered.find((c) => c.id === city?.observations[0]?.camera_id) ??
    filtered[0];
  const obs = city?.observations.find((o) => o.camera_id === camera?.id);
  const network = networks.find((n) => n.city === selected);
  const roadContext = traffic?.cities.find((c) => c.city === selected);
  const weather = traffic?.weather.find((w) => w.city === selected);
  const event = roadContext?.events.find((e) => e.id === eventId);
  return (
    <Shell
      title="City intelligence"
      eyebrow="OFFICIAL OBSERVATIONS / ADVISORY RESEARCH"
      action={
        <Link
          className="button"
          href={`/twin?city=${selected}&camera=${camera?.id ?? ""}`}
        >
          Open digital twin
        </Link>
      }
    >
      <p className="city-notice">
        Recorded official source checks. Retrieval time is shown separately from
        capture time, which these sampled feeds do not verify. Snapshots do not
        establish speeds, flow or trajectories.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="city-toolbar">
        <label>
          City{" "}
          <select
            aria-label="Select city"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setCameraId(null);
              setEventId(null);
              setSearch("");
            }}
          >
            {CITY_CHOICES.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <button className="button" onClick={() => setGeometry((v) => !v)}>
          {geometry ? "Show camera coverage" : "Show OSM corridor"}
        </button>
        <label>
          Find a camera
          <input
            aria-label="Search city cameras"
            type="search"
            placeholder="Road, intersection or camera ID"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div className="city-content-area" aria-busy={!city && !error}>
        {city ? (
          <>
            <div className="city-metrics">
              <div>
                <span>CATALOG CAMERAS</span>
                <strong>{city.cameras.length}</strong>
              </div>
              <div>
                <span>IMAGES TESTED</span>
                <strong>
                  {
                    city.image_checks.filter((c) => c.status === "accessible")
                      .length
                  }{" "}
                  / {city.image_checks.length}
                </strong>
              </div>
              <div>
                <span>DATA MODE</span>
                <strong>Snapshot</strong>
              </div>
              <div>
                <span>FIELD CALIBRATION</span>
                <strong>Pending</strong>
              </div>
            </div>
            <div className="city-task-path">
              <div>
                <strong>Start with the selected observation</strong>
                <p>
                  {obs
                    ? "This source has a genuine processed observation. Review its visible counts and coverage, then inspect the matched twin workflow."
                    : "This catalog source has not been processed. Choose a highlighted sampled camera or inspect the saved city study."}
                </p>
              </div>
              <Link
                className="button secondary"
                href={`/twin?city=${selected}&camera=${camera?.id ?? ""}`}
              >
                Inspect observation → twin
              </Link>
            </div>
            <div className="city-columns">
              <section className="city-panel">
                <h2>{geometry ? "Exploratory corridor" : "Camera coverage"}</h2>
                <CityMap
                  key={`${selected}:${geometry}:${search}`}
                  city={mapCity}
                  network={geometry ? network : undefined}
                  onCamera={setCameraId}
                  events={roadContext?.events}
                  onEvent={setEventId}
                />
                <p>
                  {geometry
                    ? network?.calibration.demand
                    : "Select a camera marker to inspect source coverage. Gray cameras were discovered but their images were not sampled."}
                </p>
                <p>
                  {filtered.length} matching cameras. Amber markers indicate
                  source-reported road events; select one to inspect its report.
                </p>
                {event && (
                  <div role="status">
                    <h3>Reported road event</h3>
                    <p>{event.description}</p>
                    <p>
                      {event.source_status} · source update{" "}
                      {event.source_modified_at ?? "Not exposed"} · retrieved{" "}
                      {event.retrieved_at}. ATLAS has not independently
                      confirmed this event or applied it to the simulation.
                    </p>
                  </div>
                )}
                {roadContext && (
                  <p>
                    Event source: {roadContext.status}.{" "}
                    {roadContext.reason ?? roadContext.coverage}
                  </p>
                )}
                {weather?.status === "available" && (
                  <p>
                    Regional weather: {weather.temperature_c} °C, wind{" "}
                    {weather.wind_speed_knots} knots · station {weather.station}{" "}
                    · observed {weather.observed_at}. Airport context does not
                    establish conditions at each intersection.
                  </p>
                )}
              </section>
              <section className="city-panel">
                <h2>Observation inspection</h2>
                <label>
                  Camera{" "}
                  <select
                    aria-label="Select camera"
                    value={camera?.id ?? ""}
                    onChange={(e) => setCameraId(e.target.value)}
                  >
                    {filtered.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <h3>{camera?.name}</h3>
                <p>Orientation: {camera?.orientation ?? "Not exposed"}</p>
                <p>Source declaration: {camera?.availability ?? "Unknown"}</p>
                {obs ? (
                  <>
                    <dl className="city-details">
                      <dt>Retrieved</dt>
                      <dd>{obs.retrieved_at}</dd>
                      <dt>Capture timestamp</dt>
                      <dd>Not verified</dd>
                      <dt>HTTP Last-Modified</dt>
                      <dd>{obs.source_last_modified_at ?? "Not exposed"}</dd>
                      <dt>Check-time freshness proxy</dt>
                      <dd>
                        {obs.freshness_status ?? "Unknown"}
                        {obs.freshness_proxy_seconds != null
                          ? ` · ${Math.round(obs.freshness_proxy_seconds)} s since HTTP modification`
                          : ""}
                        ; not capture age
                      </dd>
                      <dt>Visible object counts</dt>
                      <dd>
                        {Object.entries(obs.counts ?? {})
                          .map(([k, v]) => `${v} ${k}`)
                          .join(", ") || "No detections above threshold"}
                      </dd>
                      <dt>Inference</dt>
                      <dd>
                        {obs.inference_ms?.toFixed(1)} ms (single image, not
                        throughput)
                      </dd>
                      <dt>Model score</dt>
                      <dd>
                        {obs.confidence?.toFixed(2) ?? "No detections"}; not
                        calibrated accuracy
                      </dd>
                    </dl>
                    <p>{obs.limitations}</p>
                  </>
                ) : (
                  <p>
                    No image sample was collected for this camera. Catalog
                    presence does not establish feed health.
                  </p>
                )}
                <p>Last source check: {city.checked_at}</p>
                <a
                  href={city.settings.licensing.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Source terms and attribution ↗
                </a>
                <p>{city.settings.licensing.status}</p>
              </section>
            </div>
            <CityEvidenceV4 city={selected} />
            <Link className="button" href={`/calibration?city=${selected}`}>
              Inspect calibration quality →
            </Link>
          </>
        ) : (
          !error && <EvidenceLoading label="Loading recorded source checks…" />
        )}
      </div>
    </Shell>
  );
}
