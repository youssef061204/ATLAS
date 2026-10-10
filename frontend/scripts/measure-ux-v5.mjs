import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import os from "node:os";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3130";
const browser = await chromium.launch();
const scans = [];
try {
  for (const width of [1440, 390]) {
    for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
      for (const route of ["calibration", "studio", "pilot"]) {
        const context = await browser.newContext({
          viewport: { width, height: 900 },
        });
        const page = await context.newPage();
        const errors = [];
        const failed = [];
        page.on("pageerror", (error) => errors.push(error.message));
        page.on("response", (response) => {
          if (response.status() >= 400)
            failed.push({
              status: response.status(),
              path: new URL(response.url()).pathname,
            });
        });
        await page.addInitScript(() => {
          window.__atlasPerf = { lcp_ms: null, cls: 0, long_tasks_ms: [] };
          for (const type of [
            "largest-contentful-paint",
            "layout-shift",
            "longtask",
          ]) {
            if (PerformanceObserver.supportedEntryTypes.includes(type))
              new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                  if (type === "largest-contentful-paint")
                    window.__atlasPerf.lcp_ms = entry.startTime;
                  if (type === "layout-shift" && !entry.hadRecentInput)
                    window.__atlasPerf.cls += entry.value;
                  if (type === "longtask")
                    window.__atlasPerf.long_tasks_ms.push(entry.duration);
                }
              }).observe({ type, buffered: true });
          }
        });
        const url = `${base}/${route}?city=${city}&cohort=atlas-5&case=high`;
        await page.goto(url, { waitUntil: "networkidle" });
        if (route === "calibration") {
          await page
            .getByRole("table", { name: "ATLAS 5 forecast regression results" })
            .waitFor();
          await page
            .getByText("View exact measurement values", { exact: true })
            .click();
        }
        if (route === "studio") {
          await page
            .getByRole("heading", {
              name: `All 10 paired final seeds: ${city} / high`,
            })
            .waitFor();
          await page
            .getByRole("button", { name: "Play recorded replay" })
            .click();
        }
        if (route === "pilot")
          await page
            .getByRole("button", { name: "Export pilot assessment" })
            .waitFor();
        const taskReady = await page.evaluate(() => performance.now());
        const timings = await page.evaluate(async () => {
          const intervals = [];
          let previous;
          await new Promise((resolve) => {
            const tick = (time) => {
              if (previous !== undefined) intervals.push(time - previous);
              previous = time;
              if (intervals.length < 120) requestAnimationFrame(tick);
              else resolve();
            };
            requestAnimationFrame(tick);
          });
          const resources = performance.getEntriesByType("resource");
          return {
            ...window.__atlasPerf,
            observed_raf_fps:
              1000 / (intervals.reduce((a, b) => a + b, 0) / intervals.length),
            raf_sample_frames: intervals.length,
            js_heap_used_bytes: performance.memory?.usedJSHeapSize ?? null,
            transfer_bytes: resources.reduce(
              (sum, item) => sum + item.transferSize,
              0,
            ),
            recorded_payloads: resources
              .filter((r) => r.name.includes("/demo/cities/v5/"))
              .map((r) => ({
                path: new URL(r.name).pathname,
                transfer_bytes: r.transferSize,
                duration_ms: r.duration,
              })),
            horizontal_overflow_px: Math.max(
              0,
              document.documentElement.scrollWidth - innerWidth,
            ),
          };
        });
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        scans.push({
          route,
          city,
          width,
          task_ready_ms: taskReady,
          ...timings,
          violations: axe.violations,
          incomplete: axe.incomplete.map((r) => ({
            id: r.id,
            nodes: r.nodes.length,
          })),
          page_errors: errors,
          failed_responses: failed,
        });
        console.log(
          `${width}px ${route}/${city}: ${axe.violations.length} axe violations, ready ${taskReady.toFixed(0)}ms, LCP ${timings.lcp_ms?.toFixed(0)}ms`,
        );
        await context.close();
      }
    }
  }
  const sources = {};
  for (const file of [
    "components/calibration-dashboard.tsx",
    "components/control-study-v5.tsx",
    "components/research-evidence-v5.tsx",
    "components/pilot-studio.tsx",
    "components/shell.tsx",
    "components/landing.tsx",
    "components/city-map.tsx",
    "app/globals.css",
    "app/layout.tsx",
    "public/fonts/sources.json",
    "scripts/measure-ux-v5.mjs",
  ])
    sources[`frontend/${file}`] = createHash("sha256")
      .update(await readFile(file))
      .digest("hex");
  const evidence = {
    schema_version: "atlas-browser-laboratory-5.0",
    measured_at: new Date().toISOString(),
    base_url: base,
    browser: await browser.version(),
    build_id: await readFile(".next/BUILD_ID", "utf8"),
    host: {
      cpu: os.cpus()[0]?.model,
      logical_processors: os.cpus().length,
      platform: os.platform(),
    },
    measured_source_sha256: sources,
    scans,
    scope:
      "Actual local production build, fresh context per city/route/viewport, no throttling. Studio playback active during frame-cadence sampling. One sample per case; shared host load.",
    limitations: [
      "Local LCP/CLS are not field Core Web Vitals; task readiness is not TTI, RAF cadence is not processing FPS or measured interaction INP.",
      "Chromium heap is not full process RSS. Automated axe checks are not WCAG certification or human usability; participants: 0.",
      "The retained initial build and current build each have one sample per case; no statistically supported frontend speedup claimed.",
    ],
  };
  await writeFile(
    "../artifacts/cities/v5/ux-performance.json",
    JSON.stringify(evidence, null, 2),
  );
  if (
    scans.some(
      (r) =>
        r.violations.length ||
        r.page_errors.length ||
        r.failed_responses.length ||
        r.horizontal_overflow_px > 2,
    )
  )
    process.exitCode = 1;
} finally {
  await browser.close();
}
