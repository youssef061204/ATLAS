import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";

test("five product areas meet automated WCAG checks on desktop and mobile", async ({
  page,
}, testInfo) => {
  test.setTimeout(300000); // Aggregate budget for ten complete axe scans; normal per-page assertions remain bounded.
  const results = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const path of [
      "/cities",
      "/twin",
      "/studio",
      "/laboratory",
      "/pilot",
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("main")).not.toContainText("Loading actual");
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      results.push({
        path,
        width,
        violations: scan.violations,
        incomplete: scan.incomplete,
      });
      console.log(
        `Accessibility ${width}px ${path}: ${scan.violations.length} violations`,
      );
    }
  }
  await testInfo.attach("accessibility-results", {
    body: JSON.stringify(results, null, 2),
    contentType: "application/json",
  });
  await mkdir("../data", { recursive: true });
  await writeFile(
    "../data/accessibility-v3.json",
    JSON.stringify(results, null, 2),
  );
  expect(
    results.flatMap((r) =>
      r.violations.map((v) => ({
        path: r.path,
        width: r.width,
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => ({
          target: n.target,
          summary: n.failureSummary,
        })),
      })),
    ),
  ).toEqual([]);
});
