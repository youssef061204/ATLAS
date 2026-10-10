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
import { DEMO_MODE, GITHUB, request } from "@/lib/api";
import { CityMap } from "./city-map";
import type { Network } from "@/lib/cities";
import { CITY_CHOICES, useCitySelection } from "@/lib/city-selection";

export function Landing() {
  const [city, setCity] = useCitySelection();
  const [networks, setNetworks] = useState<Network[]>([]);
  const [evidence, setEvidence] = useState<{
    map50: number;
    idf1: number;
    pipeline_fps: number;
    graph_mae_5_mph: number;
  } | null>(null);
  useEffect(() => {
    let active = true;
    request<NonNullable<typeof evidence>>("/api/operations/summary-v4")
      .then((data) => {
        if (active) setEvidence(data);
      })
      .catch(() => {});
    request<{ networks: Network[] }>("/api/operations/networks")
      .then((data) => {
        if (active) setNetworks(data.networks);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const selected = CITY_CHOICES.find((choice) => choice.id === city)!;
  const network = networks.find((item) => item.city === city);
  return (
    <main className="landing">
      <div className="landing-noise" />
      <header className="landing-nav">
        <Logo />
        <nav>
          <Link href="/cities">Explore cities</Link>
          <Link href="/workspace" prefetch={false}>
            Platform
          </Link>
          <Link href="/benchmarks">Evidence</Link>
          <Link href="/about">Architecture</Link>
          <a href={GITHUB} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>
        <Link href="/workspace" prefetch={false} className="button secondary">
          {DEMO_MODE ? "Launch Demo" : "Launch workspace"}{" "}
          <ArrowUpRight size={15} />
        </Link>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-eyebrow">
            <span className="status-dot" />
            FIVE CITIES / ONE TRAFFIC INTELLIGENCE PLATFORM
          </div>
          <h1>
            Understand your city.
            <br />
            <span>Test a better flow.</span>
          </h1>
          <div
            className="hero-city-tabs"
            role="group"
            aria-label="Supported cities"
          >
            {CITY_CHOICES.map((choice) => (
              <button
                key={choice.id}
                type="button"
                aria-pressed={choice.id === city}
                onClick={() => setCity(choice.id)}
              >
                {choice.name}
              </button>
            ))}
          </div>
          <p>
            Explore official traffic observations, inspect a city-specific
            digital twin, and compare signal strategies with reproducible
            simulation evidence.
          </p>
          <div className="button-row">
            <Link href={`/twin?city=${city}`} className="button">
              Explore {selected.name} <ArrowRight size={17} />
            </Link>
            <Link
              href="/workspace"
              prefetch={false}
              className="button secondary"
            >
              {DEMO_MODE ? "Launch Demo" : "Explore the platform"}{" "}
              <ArrowUpRight size={17} />
            </Link>
            <Link href="/benchmarks" className="text-link">
              View Benchmarks <ArrowRight size={16} />
            </Link>
          </div>
          {DEMO_MODE && (
            <p className="demo-disclosure">
              PRECOMPUTED REAL-DATA DEMO · Saved official observations and
              actual simulation runs. New CV and SUMO jobs run on an authorized
              native worker. City corridors remain exploratory.
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
        <div className="hero-visual city-hero-visual">
          <div className="hero-visual-top">
            <span>
              <span className="status-dot" /> {selected.name.toUpperCase()} /
              OSM CORRIDOR
            </span>
            <span>REAL GEOMETRY</span>
          </div>
          {network ? (
            <CityMap key={city} network={network} />
          ) : (
            <div className="hero-placeholder">
              <Layers3 size={70} strokeWidth={0.6} />
            </div>
          )}
          <div className="hero-coordinate city-hero-status">
            <span>
              {network
                ? `${network.roads.length} imported road segments`
                : "Loading recorded geometry"}
            </span>
            <span>Field calibration pending</span>
          </div>
        </div>
      </section>
      <section className="landing-cities" aria-labelledby="five-city-heading">
        <div className="landing-city-heading">
          <div>
            <div className="eyebrow">START WITH A CITY</div>
            <h2 id="five-city-heading">
              Five environments. Inspectable evidence.
            </h2>
          </div>
          <Link href={`/cities?city=${city}`} className="text-link">
            Open the city map <ArrowRight size={16} />
          </Link>
        </div>
        <div
          className="landing-city-grid"
          role="group"
          aria-label="Choose a city"
        >
          {CITY_CHOICES.map((choice, index) => (
            <button
              type="button"
              key={choice.id}
              className={`landing-city-card${choice.id === city ? " selected" : ""}`}
              aria-pressed={choice.id === city}
              onClick={() => setCity(choice.id)}
            >
              <span className="mono">
                0{index + 1} <ArrowUpRight size={16} />
              </span>
              <strong>{choice.name}</strong>
              <small>{choice.region}</small>
              <span>Official observations · research twin</span>
            </button>
          ))}
        </div>
      </section>
      <div className="landing-divider">
        <span>FROM PIXELS TO BETTER DECISIONS</span>
        <ArrowDown size={16} />
        <span>ENGINEERED END TO END</span>
      </div>
      {evidence && (
        <section
          className="landing-metrics"
          aria-label="Verified real-data measurements"
        >
          {[
            [
              "UA-DETRAC mAP@50",
              evidence.map50.toFixed(3),
              "3 complete selected test sequences",
            ],
            [
              "UA-DETRAC IDF1",
              evidence.idf1.toFixed(3),
              "Production ByteTrack / TrackEval",
            ],
            [
              "CPU pipeline FPS",
              evidence.pipeline_fps.toFixed(1),
              "4,260 frames / Intel i7",
            ],
            [
              "GNN METR-LA MAE",
              evidence.graph_mae_5_mph.toFixed(3),
              "mph / 5 min / highway-domain holdout",
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
              "Inspect visible counts, source freshness and uncertainty. Continuous footage supports tracking; snapshots have narrower coverage.",
          },
          {
            Icon: Radar,
            n: "03",
            name: "Anticipate",
            description:
              "Compare measured highway forecasting models and city evidence. Their data domains and validation boundaries stay explicit.",
          },
          {
            Icon: GitBranch,
            n: "04",
            name: "Optimize",
            description:
              "Replay matched signal policies on real city geometry. Inspect delay, throughput, regressions and the assumptions behind every result.",
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
          ATLAS connects official transportation data, computer vision, traffic
          analytics, and safety-constrained simulation. Historical highway
          benchmarks and exploratory city outcomes are kept distinct.
          <Link href="/benchmarks">
            Inspect the evaluation artifacts <ArrowUpRight size={15} />
          </Link>
        </p>
      </section>
      <footer className="landing-footer">
        <Logo />
        <span>FIVE-CITY TRAFFIC INTELLIGENCE / ADVISORY ONLY</span>
        <Link href="/about">
          Architecture & methodology <ArrowUpRight size={14} />
        </Link>
      </footer>
    </main>
  );
}
