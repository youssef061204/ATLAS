import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

// Local laboratory timings, not field Core Web Vitals or a human usability study.
const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3120";
const phase = process.env.ATLAS_UX_PHASE ?? "baseline";
const output = path.resolve("../data/ux-v4", `${phase}.json`);
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
  ],
});
const results = [];
try {
  for (const width of [1440, 390]) {
    for (const route of [
      "/",
      "/cities",
      "/twin",
      "/studio",
      "/laboratory",
      "/pilot",
    ]) {
      const context = await browser.newContext({
        viewport: { width, height: 900 },
      });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => {
        window.__atlasPerf = {
          lcp_ms: null,
          cls: 0,
          long_tasks_ms: [],
          events_ms: [],
        };
        for (const [type, callback] of [
          [
            "largest-contentful-paint",
            (entries) => {
              window.__atlasPerf.lcp_ms = entries.at(-1)?.startTime ?? null;
            },
          ],
          [
            "layout-shift",
            (entries) => {
              for (const item of entries)
                if (!item.hadRecentInput) window.__atlasPerf.cls += item.value;
            },
          ],
          [
            "longtask",
            (entries) => {
              window.__atlasPerf.long_tasks_ms.push(
                ...entries.map((item) => item.duration),
              );
            },
          ],
          [
            "event",
            (entries) => {
              window.__atlasPerf.events_ms.push(
                ...entries
                  .filter((item) => item.interactionId)
                  .map((item) => item.duration),
              );
            },
          ],
        ]) {
          if (PerformanceObserver.supportedEntryTypes.includes(type))
            new PerformanceObserver((list) =>
              callback(list.getEntries()),
            ).observe({
              type,
              buffered: true,
              ...(type === "event" ? { durationThreshold: 16 } : {}),
            });
        }
      });
      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      const ready =
        route === "/cities"
          ? page.getByRole("button", { name: "Zoom map in" }).first()
          : route === "/twin"
            ? page.getByRole("heading", { name: "State with uncertainty" })
            : route === "/studio"
              ? page.getByRole("button", { name: "Zoom map in" }).first()
              : route === "/laboratory"
                ? page.getByRole("heading", { name: /AI laboratory/i }).first()
                : route === "/pilot"
                  ? page.getByRole("heading", { name: "Pilot assumptions" })
                  : page.locator("h1");
      await ready.waitFor({ timeout: 60000 });
      const taskReady = await page.evaluate(() => performance.now());
      const switches = [];
      if (route === "/cities") {
        for (const city of [
          "london",
          "seattle",
          "austin",
          "calgary",
          "toronto",
        ]) {
          const start = performance.now();
          await page
            .getByLabel("Select city", { exact: true })
            .selectOption(city);
          await page.waitForFunction(
            (selected) =>
              document.querySelector('select[aria-label="Select city"]')
                ?.value === selected,
            city,
          );
          await page.evaluate(
            () =>
              new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)),
              ),
          );
          switches.push({
            city,
            action_to_two_animation_frames_ms: performance.now() - start,
          });
        }
        await page.getByRole("button", { name: "Zoom map in" }).first().click();
      }
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
        const nav = performance.getEntriesByType("navigation")[0];
        const resources = performance.getEntriesByType("resource");
        return {
          ...window.__atlasPerf,
          dom_content_loaded_ms: nav.domContentLoadedEventEnd,
          load_ms: nav.loadEventEnd,
          observed_raf_fps:
            1000 /
            (intervals.reduce((sum, value) => sum + value, 0) /
              intervals.length),
          raf_sample_frames: intervals.length,
          js_heap_used_bytes: performance.memory?.usedJSHeapSize ?? null,
          transfer_bytes: resources.reduce(
            (sum, item) => sum + item.transferSize,
            0,
          ),
          api: resources
            .filter((item) => item.name.includes("/api/"))
            .map((item) => ({
              path: new URL(item.name).pathname,
              duration_ms: item.duration,
              transfer_bytes: item.transferSize,
            })),
          horizontal_overflow_px: Math.max(
            0,
            document.documentElement.scrollWidth - innerWidth,
          ),
        };
      });
      results.push({
        route,
        width,
        task_ready_ms: taskReady,
        ...timings,
        city_switches: switches,
        page_errors: errors,
      });
      console.log(
        `${phase}: ${width}px ${route}, ready=${taskReady.toFixed(0)}ms, LCP=${timings.lcp_ms?.toFixed(0)}ms`,
      );
      await context.close();
    }
  }
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(
    output,
    JSON.stringify(
      {
        phase,
        measured_at: new Date().toISOString(),
        base_url: base,
        browser: await browser.version(),
        next_build_id: await fs
          .readFile(".next/BUILD_ID", "utf8")
          .catch(() => null),
        host: {
          platform: os.platform(),
          cpu: os.cpus()[0]?.model,
          logical_processors: os.cpus().length,
        },
        protocol:
          "One fresh browser context per route and viewport; no CPU/network throttling; actual production Next.js server; 120 requestAnimationFrame intervals after readiness. Local software rendering. Event timing is observed interaction duration, not a field INP score; task readiness is not TTI.",
        results,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
