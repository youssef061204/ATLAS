export type Vec = [number, number];
export type ObjectState = {
  id: number;
  class: string;
  t: number;
  image: Vec;
  world: Vec;
  bbox: number[];
  confidence: number;
  speed: number;
  velocity: Vec;
  heading: number;
  acceleration: number;
  stopped: boolean;
  stopped_duration: number;
  direction: string;
  regions: string[];
};
export type Track = {
  id: number;
  class: string;
  points: ObjectState[];
  stopped_duration: number;
  entry_time: number | null;
  exit_time: number | null;
};
export type Metric = {
  t: number;
  active_objects: number;
  vehicles: number;
  pedestrians: number;
  cyclists: number;
  vehicles_per_minute: number;
  average_speed: number;
  median_speed: number;
  speed_unit: string;
  queue_length: number;
  max_queue: number;
  occupancy: number;
  throughput: number;
  average_stop_duration: number;
  dwell_time: number;
  approaches: Record<string, number>;
};
export type SafetyEvent = {
  id: string;
  t: number;
  participants: number[];
  type: string;
  severity: string;
  ttc: number | null;
  separation: number | null;
  risk_score: number;
  confidence: number;
  explanation: string;
  ml_score: number | null;
};
export type Calibration = {
  image: Vec[];
  world: Vec[];
  verified: boolean;
  note: string;
};
export type Region = {
  id: string;
  kind:
    | "inbound"
    | "outbound"
    | "crosswalk"
    | "intersection"
    | "waiting"
    | "stop_line";
  polygon: Vec[];
  direction: "N" | "E" | "S" | "W" | null;
};
export type CameraConfig = {
  calibration: Calibration | null;
  detector_profile: "coco" | "aerial";
  regions: Region[];
  confidence: number;
  resolution: number;
  sample_every: number;
  tracker: string;
};
export type Video = {
  id: string;
  filename: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  intersection_id: string;
  metadata: {
    duration?: number;
    width?: number;
    height?: number;
    cached?: boolean;
    live_metric?: Metric;
  };
};
export type Result = {
  scene?: { homography: number[][] | null };
  video_id: string;
  metadata: {
    fps: number;
    frame_count: number;
    duration: number;
    width: number;
    height: number;
  };
  frames: { t: number; index: number; objects: ObjectState[] }[];
  tracks: Track[];
  metrics: Metric[];
  events: SafetyEvent[];
  config: CameraConfig;
  summary: {
    unique_tracks: number;
    classes: Record<string, number>;
    vehicles: number;
    pedestrians: number;
    cyclists: number;
    calibrated: boolean;
    throughput: number;
    max_queue: number;
  };
  forecast: {
    status: string;
    reason?: string;
    model?: string;
    target?: string;
    scope?: string;
    predictions: {
      horizon_minutes: number;
      value: number;
      lower: number;
      upper: number;
    }[];
  };
  performance: {
    processed_fps: number;
    wall_seconds: number;
    processed_frames: number;
    device: string;
    model: string;
    inference_ms: Record<string, number>;
  };
  provenance: {
    cached?: boolean;
    sample_scope?: string;
    replay_stride?: number;
    generated_at: string;
    source: string;
    pipeline: string;
    accuracy_evaluation: string;
  };
};
export type SimMetrics = {
  delay: number;
  queue?: number;
  mean_queue?: number;
  max_queue?: number;
  cleared?: number;
  throughput: number;
  stops: number;
  pedestrian_wait: number;
  arrived?: number;
  unfinished?: number;
};
export type SimFrame = {
  t: number;
  phase: number;
  signal: string;
  vehicles: {
    id: number;
    approach: number;
    position: number;
    velocity: number;
  }[];
  metrics: SimMetrics;
};
export type SimRun = {
  policy: string;
  greens: number[] | null;
  metrics: SimMetrics;
  frames: SimFrame[];
};
export type Simulation = {
  id: string;
  scope: string;
  runs: SimRun[];
  improvement_pct: Record<string, number | null>;
  search: {
    candidates: number;
    tuning_seeds: number[];
    selected: { greens: number[]; objective: number };
  };
  settings: { duration: number; demand: number[]; seed: number };
};
