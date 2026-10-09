"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  ChartNoAxesCombined,
  GitBranch,
  Layers3,
  Radar,
  ScanLine,
} from "lucide-react";
import { Logo } from "./shell";
import { Twin } from "./twin";
import type { SimFrame } from "@/lib/types";
import { DEMO_MODE, GITHUB, request } from "@/lib/api";
import type { RealArtifact } from "./real-benchmarks";

export function Landing() {
  const [frames, setFrames] = useState<SimFrame[]>([]);
  const [time, setTime] = useState(0);
  const [evidence, setEvidence] = useState<Record<string, RealArtifact>>({});
  const [graphMae, setGraphMae] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    request<{ real_world?: Record<string, RealArtifact> }>("/api/benchmarks")
      .then((data) => {
        if (active) setEvidence(data.real_world || {});
      })
      .catch(() => {});
    request<{
      results: {
        horizon_minutes: number;
        selected_on_validation: string;
        models: { model: string; metrics: { mae: number } }[];
      }[];
    }>("/api/operations/models/graph")
      .then((data) => {
        const horizon = data.results.find((row) => row.horizon_minutes === 5);
        const selected = horizon?.models.find(
          (model) => model.model === horizon.selected_on_validation,
        );
        if (active && selected) setGraphMae(selected.metrics.mae);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    fetch("/preview.json")
      .then((r) => r.json())
      .then(setFrames)
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!frames.length) return;
    const id = setInterval(() => setTime((t) => (t + 1) % frames.length), 180);
    return () => clearInterval(id);
  }, [frames.length]);
  return (
    <main className="landing">
      <div className="landing-noise" />
      <header className="landing-nav">
        <Logo />
        <nav>
          <Link href="/cities">Explore cities</Link>
          <Link href="/workspace">Platform</Link>
          <Link href="/benchmarks">Evidence</Link>
          <Link href="/about">Architecture</Link>
          <a href={GITHUB} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
        <Link href="/workspace" className="button secondary">
          {DEMO_MODE ? "Launch Demo" : "Launch workspace"}{" "}
          <ArrowUpRight size={15} />
        </Link>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-eyebrow">
            <span className="status-dot" />
            TRAFFIC DIGITAL TWIN & ADAPTIVE INTELLIGENCE
          </div>
          <h1>
            Read the road.
            <br />
            <span>Reimagine the flow.</span>
          </h1>
          <p>
            Turn traffic footage into a living digital twin.
            <br />
            See movement. Understand conflicts.
            <br />
            Test a better signal strategy.
          </p>
          <div className="button-row">
            <Link href="/twin" className="button secondary">
              Explore the intelligence loop <ArrowRight size={17} />
            </Link>
            <Link href="/workspace" className="button">
              {DEMO_MODE ? "Launch Demo" : "Explore the platform"}{" "}
              <ArrowUpRight size={17} />
            </Link>
            <Link href="/benchmarks" className="text-link">
              View Benchmarks <ArrowRight size={16} />
            </Link>
          </div>
          {DEMO_MODE && (
            <p className="demo-disclosure">
              Precomputed real CV replay. Interactive tracks, analytics, and
              measured benchmarks. New footage processing runs in the local
              Python application.
            </p>
          )}
          <div className="hero-stack">
            <span>COMPUTER VISION</span>
            <i />
            <span>TRAJECTORY INTELLIGENCE</span>
            <i />
            <span>SIGNAL OPTIMIZATION</span>
          </div>
        </div>
        <div className="hero-visual">
          <div className="hero-visual-top">
            <span>
              <span className="status-dot" /> INTERSECTION / DIGITAL TWIN
            </span>
            <span>01</span>
          </div>
          {frames[time] ? (
            <Twin simFrame={frames[time]} />
          ) : (
            <div className="hero-placeholder">
              <Layers3 size={70} strokeWidth={0.6} />
            </div>
          )}
          <div className="hero-coordinate">
            40.7128° N <span>/</span> CONCEPTUAL INTERSECTION
          </div>
          <div className="hero-float">
            <div>
              <span className="eyebrow">MODEL TRAFFIC / SEEDED SIMULATION</span>
              <strong>
                {frames[time]?.metrics.cleared ?? "—"}
                <small>vehicles cleared</small>
              </strong>
            </div>
            <div className="mini-signal">
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>
      </section>
      <div className="landing-divider">
        <span>FROM PIXELS TO BETTER DECISIONS</span>
        <ArrowDown size={16} />
        <span>ENGINEERED END TO END</span>
      </div>
      {evidence.real_detection && (
        <section
          className="landing-metrics"
          aria-label="Verified real-data measurements"
        >
          {[
            [
              "UA-DETRAC mAP@50",
              evidence.real_detection.metrics.map50?.toFixed(3),
              "3 complete selected test sequences",
            ],
            [
              "UA-DETRAC IDF1",
              evidence.real_tracking?.metrics.IDF1?.toFixed(3),
              "Production ByteTrack / TrackEval",
            ],
            [
              "CPU pipeline FPS",
              evidence.real_video_pipeline?.metrics.pipeline_fps?.toFixed(1),
              "4,260 frames / Intel i7",
            ],
            [
              graphMae === null ? "Original METR-LA MAE" : "GNN METR-LA MAE",
              graphMae?.toFixed(3) ??
                evidence.real_forecasting?.metrics.horizons?.[
                  "5"
                ]?.atlas_gradient_boosting.mae.toFixed(3),
              graphMae === null
                ? "mph / 5 min / 207 sensors"
                : "mph / 5 min / shared historical holdout",
            ],
          ].map(([label, value, scope]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value || "Unmeasured"}</strong>
              <small>{scope}</small>
            </div>
          ))}
        </section>
      )}
      <section className="landing-features">
        {[
          {
            Icon: ScanLine,
            n: "01",
            name: "Observe",
            description:
              "Pretrained YOLO and persistent tracking turn each frame into structured road-user trajectories.",
          },
          {
            Icon: ChartNoAxesCombined,
            n: "02",
            name: "Understand",
            description:
              "Flow, queues, dwell time, and calibrated motion expose what is happening on the road.",
          },
          {
            Icon: Radar,
            n: "03",
            name: "Anticipate",
            description:
              "Projected conflicts and causal forecasts make uncertainty visible and events reviewable.",
          },
          {
            Icon: GitBranch,
            n: "04",
            name: "Optimize",
            description:
              "Replay equal demand across three signal policies. Compare actual simulated delay and throughput.",
          },
        ].map((f) => (
          <article key={f.n}>
            <div>
              <f.Icon size={24} strokeWidth={1.3} />
              <span>{f.n}</span>
            </div>
            <h2>
              {f.name}
              <span>.</span>
            </h2>
            <p>{f.description}</p>
          </article>
        ))}
      </section>
      <section className="landing-proof">
        <div>
          <div className="eyebrow">BUILT TO BE INSPECTED</div>
          <h2>
            Every metric has a source.
            <br />
            Every experiment has a seed.
          </h2>
        </div>
        <p>
          ATLAS connects computer vision, traffic analytics, and simulation in
          one local research platform. No LLM dependency. No hidden estimates.
          <Link href="/benchmarks">
            Inspect the evaluation artifacts <ArrowUpRight size={15} />
          </Link>
        </p>
      </section>
      <footer className="landing-footer">
        <Logo />
        <span>INTERSECTION INTELLIGENCE / V1.0</span>
        <Link href="/about">
          Architecture & methodology <ArrowUpRight size={14} />
        </Link>
      </footer>
    </main>
  );
}
