export type Observation = {
  id: string;
  camera_id: string;
  retrieved_at: string;
  captured_at: string | null;
  source_last_modified_at: string | null;
  freshness_status?: string;
  freshness_proxy_seconds?: number | null;
  counts?: Record<string, number>;
  inference_ms?: number;
  confidence: number | null;
  quality: { brightness: number; laplacian_variance: number };
  limitations?: string;
};
export type RoadEvent = {
  id: string;
  city: string;
  lat: number;
  lon: number;
  description: string;
  reported_kind: string;
  source_status: string;
  source_modified_at: string | null;
  retrieved_at: string;
  confirmed_by_atlas: boolean;
};
export type TrafficContext = {
  cities: {
    city: string;
    status: string;
    reason?: string;
    retrieved_at: string;
    coverage: string;
    source: string;
    events: RoadEvent[];
  }[];
  weather: {
    city: string;
    station: string;
    status: string;
    observed_at?: string;
    temperature_c?: number;
    wind_speed_knots?: number;
    scope?: string;
  }[];
};
export type CityReport = {
  city: string;
  checked_at: string;
  status: string;
  reason?: string;
  settings: {
    name: string;
    attribution: string;
    licensing: { url: string; status: string };
  };
  cameras: {
    id: string;
    name: string;
    lat: number;
    lon: number;
    orientation: string | null;
    availability: string;
    kind: string;
  }[];
  observations: Observation[];
  image_checks: { camera_id: string; status: string; reason?: string }[];
};
export type Network = {
  city: string;
  mode: string;
  signals: { id: string; lon: number | null; lat: number | null }[];
  roads: { id: string; coordinates: [number, number][] }[];
  calibration: { status: string; demand: string; signal_timings: string };
};
export type Run = {
  city: string;
  policy: string;
  seed: number;
  duration: number;
  scenario: string;
  network_sha256: string;
  routes_sha256: string;
  metrics: Record<string, number>;
  trace: {
    t: number;
    queue: number;
    vehicles?: {
      id: string;
      lon: number | null;
      lat: number | null;
      speed_m_s: number;
    }[];
    signals: Record<
      string,
      {
        phase: number;
        state: string;
        reason: string;
        queue: number;
        execution: string;
      }
    >;
  }[];
  decisions: {
    intersection: string;
    t: number;
    selected: number;
    reason: string;
    horizon_s?: number;
    objective?: number;
    arrival_uncertainty?: number[];
    alternatives?: { phase: number; first_stage_cost: number }[];
    fluid_objective?: number;
    constraints: number[];
  }[];
};
export type Experiments = {
  scope: string;
  paired?: {
    city: string;
    baseline: string;
    pairs: number;
    paired_difference_ci95: number[];
    paired_percent_ci95: number[];
  }[];
  runs: Run[];
  summaries: {
    city: string;
    policy: string;
    seeds: number;
    mean_delay_s: number;
    sd: number | null;
    ci95: number[] | null;
    decision_ms_p95: number;
    comparisons?: {
      baseline: string;
      n: number;
      mean_paired_reduction_pct: number;
      ci95: number[];
    }[];
  }[];
  failures: { city: string; policy: string; reason: string }[];
};
export const POLICY: Record<string, string> = {
  fixed: "Fixed timing",
  max_pressure: "Max-pressure",
  original_mpc: "Frozen ATLAS MPC",
  risk_mpc: "ATLAS 2.0 prototype",
  network_mpc: "ATLAS 4.0 cached MPC",
  cached_original: "Cached original MPC",
  portfolio_v5: "Experimental ATLAS 5 portfolio",
  actuated: "Actuated control",
  cooperative_q: "Experimental cooperative Q",
  marl: "Experimental cooperative Q",
};
