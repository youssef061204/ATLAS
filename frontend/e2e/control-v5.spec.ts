import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs/promises";

test("ATLAS 5 genuine paired replays cover every city and robustness scenario", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/studio?city=toronto&cohort=atlas-5");
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await page
      .getByLabel("Simulation city", { exact: true })
      .selectOption(city);
    for (const scenario of [
      "low",
      "nominal",
      "high",
      "incident",
      "outage",
      "shift",
    ]) {
      await page.getByLabel("Robustness scenario").selectOption(scenario);
      await expect(
        page.getByRole("heading", {
          name: `All 10 paired final seeds: ${city} / ${scenario}`,
        }),
      ).toBeVisible();
      await expect(
        page
          .getByRole("table", { name: "Held-out controller comparison" })
          .locator("tbody tr"),
      ).toHaveCount(7);
      await expect(
        page.getByText("Actual paired seed 55301.", { exact: false }).first(),
      ).toBeVisible();
      await expect(page.getByLabel("Network replay timeline")).toHaveAttribute(
        "max",
        "59",
      );
    }
    expect(await new AxeBuilder({ page }).analyze()).toMatchObject({
      violations: [],
    });
  }
  await page
    .getByLabel("Simulation city", { exact: true })
    .selectOption("toronto");
  await page.getByLabel("Robustness scenario").selectOption("low");
  await expect(
    page.getByText("This cell regressed.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("worst episode: failed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Play recorded replay" }).click();
  await expect
    .poll(async () =>
      Number(await page.getByLabel("Network replay timeline").inputValue()),
    )
    .toBeGreaterThan(0);
  await page.getByRole("button", { name: "Pause recorded replay" }).click();
  await page.getByLabel("Baseline controller").selectOption("cached_original");
  await expect(
    page.getByRole("heading", {
      name: "Cached original MPC",
      level: 2,
      exact: true,
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("ATLAS 5 mobile comparison exports authentic seeds and keeps field savings unverified", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/studio?city=seattle&cohort=atlas-5&case=high");
  await expect(
    page.getByRole("heading", {
      name: "All 10 paired final seeds: seattle / high",
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - innerWidth,
    ),
  ).toBeLessThanOrEqual(2);
  expect(await new AxeBuilder({ page }).analyze()).toMatchObject({
    violations: [],
  });
  await page
    .getByRole("link", { name: "Export this pilot assessment" })
    .click();
  await expect(page.getByLabel("Pilot evidence cohort")).toHaveValue("atlas-5");
  await expect(page.getByLabel("Pilot city")).toHaveValue("seattle");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: /Export.*assessment/i }).click();
  const file = await (await download).path();
  const report = JSON.parse(await fs.readFile(file!, "utf8"));
  expect(report).toMatchObject({
    city: "seattle",
    evidence_cohort: "atlas-5",
    scenario_case: "high",
    field_validated: false,
    production_promoted: false,
  });
  expect(
    [
      ...new Set(
        report.simulation_inputs.map((row: { seed: number }) => row.seed),
      ),
    ].sort(),
  ).toEqual(Array.from({ length: 10 }, (_, i) => 55301 + i));
  expect(report.paired_delay_ci95_s).toHaveLength(2);
});
