"use client";
import Link from "next/link";
import { DEMO_MODE } from "@/lib/api";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowUpRight,
  AudioLines,
  Box,
  ChartNoAxesCombined,
  ChevronRight,
  CircleDot,
  Cpu,
  GitBranch,
  Layers3,
  Radar,
  ScanLine,
} from "lucide-react";

const links = [
  ["/cities", "Explore cities", CircleDot],
  ["/twin", "Digital twin", Layers3],
  ["/studio", "Optimization studio", GitBranch],
  ["/laboratory", "AI laboratory", Cpu],
  ["/pilot", "Pilot builder", Box],
] as const;
const detailLinks = [
  ["/workspace", "Video intelligence", ScanLine],
  ["/analytics", "Traffic analytics", ChartNoAxesCombined],
  ["/safety", "Safety intelligence", Radar],
  ["/forecast", "Forecasting", Activity],
  ["/optimization", "Signal laboratory", GitBranch],
  ["/benchmarks", "Evaluation", Cpu],
] as const;
export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="ATLAS home">
      <Layers3 size={27} strokeWidth={1.6} />
      <span>
        ATLAS<span className="logo-dot">.</span>
      </span>
    </Link>
  );
}
export function Shell({
  children,
  title,
  eyebrow,
  action,
}: {
  children: React.ReactNode;
  title: string;
  eyebrow: string;
  action?: React.ReactNode;
}) {
  const path = usePathname();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <div className="sidebar-label">INTELLIGENCE PLATFORM</div>
        <nav>
          {links.map(([href, name, Icon]) => (
            <Link
              key={href}
              href={href}
              aria-label={name}
              aria-current={path === href ? "page" : undefined}
              className={path === href ? "nav-link active" : "nav-link"}
            >
              <Icon size={18} />
              <span>{name}</span>
              {path === href && <ChevronRight size={14} />}
            </Link>
          ))}
        </nav>
        <details
          open={detailLinks.some(([href]) => path === href)}
          className="research-navigation"
        >
          <summary>Detailed analysis & benchmarks</summary>
          <nav>
            {detailLinks.map(([href, name, Icon]) => (
              <Link
                key={href}
                href={href}
                aria-label={name}
                aria-current={path === href ? "page" : undefined}
                className={path === href ? "nav-link active" : "nav-link"}
              >
                <Icon size={18} />
                <span>{name}</span>
              </Link>
            ))}
          </nav>
        </details>
        <div className="sidebar-site">
          <CircleDot size={17} />
          <div>
            <strong>Traffic research platform</strong>
            <span>
              {DEMO_MODE
                ? "Precomputed real CV demo"
                : "Local research workspace"}
            </span>
          </div>
        </div>
        <div className="sidebar-bottom">
          <Link href="/about">
            <Box size={16} /> System architecture <ArrowUpRight size={13} />
          </Link>
          <div>
            <AudioLines size={14} /> RESEARCH <span>ADVISORY ONLY</span>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span>
            <span className="status-dot" />
            {DEMO_MODE ? "PRECOMPUTED DEMO" : "LOCAL WORKSPACE"}{" "}
            <span className="topbar-slash">/</span> {eyebrow}
          </span>
          <Link href="/about">
            ENGINEERED FOR OBSERVABILITY <ArrowUpRight size={13} />
          </Link>
        </header>
        <div className="page-head">
          <div>
            <div className="eyebrow">{eyebrow}</div>
            <h1>{title}</h1>
          </div>
          {action}
        </div>
        {children}
        <footer className="app-footer">
          <span>ATLAS / TRAFFIC DIGITAL TWIN</span>
          <span>Measured observations. Reproducible experiments.</span>
        </footer>
      </main>
    </div>
  );
}
