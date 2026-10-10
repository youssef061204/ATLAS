import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("calibration matrix preserves unavailable simulation states across five cities", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await page.goto(`/calibration?city=${city}`);
    await expect(
      page.getByRole("table").first().locator("tbody tr"),
    ).toHaveCount(5);
    await expect(
      page.getByText("0 independently validated twins", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Simulation-state comparisons pending", { exact: true }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("combobox", {
          name: "Inspect observed site / direction / study date",
        })
        .locator("option")
        .first(),
    ).toBeAttached();
    await expect(
      page.getByRole("link", { name: "4. Compare control", exact: true }),
    ).toHaveAttribute("href", `/studio?city=${city}&cohort=atlas-5`);
    await page
      .getByText("View exact measurement values", { exact: true })
      .click();
    const values = page.getByRole("table").nth(1);
    await expect(
      values.locator("tbody tr").first().locator("td").last(),
    ).toHaveText("Unavailable");
    expect(await new AxeBuilder({ page }).analyze()).toMatchObject({
      violations: [],
    });
  }
  expect(errors).toEqual([]);
});

test("calibration remains readable on mobile and handles missing evidence", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/calibration?city=calgary");
  await expect(
    page.getByText("0 independently validated twins", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(2);
  expect(await new AxeBuilder({ page }).analyze()).toMatchObject({
    violations: [],
  });
  await page.route("**/demo/cities/v5/calibration-readiness.json", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.reload();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Calibration evidence unavailable" }),
  ).toContainText("Calibration evidence unavailable");
  await expect(
    page.getByRole("button", { name: "Retry evidence" }),
  ).toBeVisible();
});
