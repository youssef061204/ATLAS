import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";
import path from "node:path";

const base = process.env.ATLAS_WEB_URL ?? "http://127.0.0.1:3125";
const cities = ["toronto", "london", "seattle", "austin", "calgary"];
const browser = await chromium.launch();
const scans = [];
try {
  for (const width of [1440, 390]) {
    const context = await browser.newContext({
      viewport: { width, height: 1000 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const route of [
      "/",
      "/studio?cohort=atlas-4&city=toronto",
      "/laboratory",
      "/pilot",
      ...cities.flatMap((city) => [
        `/cities?city=${city}`,
        `/twin?city=${city}`,
      ]),
    ]) {
      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      if (route.startsWith("/cities"))
        await page
          .getByRole("group", { name: "Official camera coordinates" })
          .waitFor();
      if (route.startsWith("/twin"))
        await page
          .getByRole("heading", { name: "State with uncertainty" })
          .waitFor();
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      scans.push({
        route,
        width,
        violations: scan.violations.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          help: violation.help,
          nodes: violation.nodes.map((node) => ({
            target: node.target,
            failure: node.failureSummary,
          })),
        })),
        incomplete: scan.incomplete.map((item) => ({
          id: item.id,
          nodes: item.nodes.length,
        })),
        horizontal_overflow_px: await page.evaluate(() =>
          Math.max(0, document.documentElement.scrollWidth - innerWidth),
        ),
      });
      console.log(
        `${width}px ${route}: ${scan.violations.length} axe violations`,
      );
      if (route.startsWith("/twin")) {
        await page
          .getByText("Inspect historical city data & forecast validation", {
            exact: true,
          })
          .click();
        await page
          .getByRole("table", {
            name: "City forecasting comparison",
            exact: true,
          })
          .waitFor();
        const expanded = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        scans.push({
          route,
          width,
          historical_evidence_expanded: true,
          violations: expanded.violations.map((violation) => ({
            id: violation.id,
            impact: violation.impact,
            help: violation.help,
            nodes: violation.nodes.map((node) => ({
              target: node.target,
              failure: node.failureSummary,
            })),
          })),
          incomplete: expanded.incomplete.map((item) => ({
            id: item.id,
            nodes: item.nodes.length,
          })),
          horizontal_overflow_px: await page.evaluate(() =>
            Math.max(0, document.documentElement.scrollWidth - innerWidth),
          ),
        });
        console.log(
          `${width}px ${route} expanded historical evidence: ${expanded.violations.length} axe violations`,
        );
      }
    }
    scans.at(-1).page_errors = errors;
    await context.close();
  }
  const output = path.resolve("../data/ux-v4/accessibility.json");
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(
    output,
    JSON.stringify(
      {
        measured_at: new Date().toISOString(),
        base_url: base,
        axe_tags: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
        scope:
          "Automated engineering checks of actual saved city evidence on desktop/mobile; not a human usability study, complete accessibility audit or WCAG certification.",
        scans,
      },
      null,
      2,
    ),
  );
  if (
    scans.some(
      (scan) =>
        scan.violations.length ||
        scan.horizontal_overflow_px > 2 ||
        scan.page_errors?.length,
    )
  )
    process.exitCode = 1;
} finally {
  await browser.close();
}
