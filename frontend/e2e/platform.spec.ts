import { expect, test } from "@playwright/test";

test("landing communicates the platform and opens the workspace", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Understand your city.",
  );
  await page
    .getByRole("link", { name: /Launch (workspace|Demo)/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Intersection intelligence" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("empty analytics gives a useful next action", async ({ page }) => {
  await page.route("**/api/videos", (route) => route.fulfill({ json: [] }));
  await page.goto("/analytics");
  await expect(page.getByText("Observations come first.")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open intersection", exact: true }),
  ).toBeVisible();
});

test("actual source overlay, seek, selection, and heatmap stay usable", async ({
  page,
}) => {
  test.skip(
    !!process.env.CI || !!process.env.ATLAS_PUBLIC_DEMO,
    "Camera setup requires the native API; public replay has separate checks",
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/workspace");
  await expect(page.getByText("ROAD USERS DETECTED")).toBeVisible();
  const slider = page.getByRole("slider", { name: "Video timeline" });
  await slider.fill("3");
  await expect
    .poll(() =>
      page.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime),
    )
    .toBeGreaterThan(2.9);
  const box = page.locator(".cv-overlay g").first();
  await expect(box).toBeVisible();
  await box.click();
  await expect(page.locator(".object-title")).toBeVisible();
  await page.getByRole("button", { name: "HEATMAP", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "HEATMAP", exact: true }),
  ).toHaveClass("selected");
  await page.getByRole("button", { name: "Camera setup" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByRole("button", { name: "Close camera setup" }).click();
  await page.screenshot({
    path: "../artifacts/screenshots/workspace.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("optimization produces equivalent-demand policy comparisons", async ({
  page,
}) => {
  test.skip(
    !!process.env.CI || !!process.env.ATLAS_PUBLIC_DEMO,
    "New processing requires the native API; public replay has separate checks",
  );
  await page.goto("/optimization");
  await page
    .getByRole("button", { name: "Optimize intersection" })
    .first()
    .click();
  await expect(
    page.getByText("ALL THREE POLICIES / FINAL METRICS"),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    page
      .getByRole("table", { name: "Historical portable simulation metrics" })
      .locator("tbody tr"),
  ).toHaveCount(3);
  await page.getByRole("button", { name: "Pause simulation" }).click();
  await page.getByRole("slider", { name: "Simulation timeline" }).fill("120");
  await expect(page.getByText("120s", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../artifacts/screenshots/optimization.png",
    fullPage: true,
  });
});

test("all data routes render generated artifacts without runtime errors", async ({
  page,
}) => {
  test.skip(!!process.env.CI, "Full integration needs the API");
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const path of [
    "analytics",
    "safety",
    "forecast",
    "benchmarks",
    "about",
  ]) {
    await page.goto(`/${path}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: `../artifacts/screenshots/${path}.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});

test("mobile workspace fits the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace");
  await expect(
    page.getByRole("heading", { name: "Intersection intelligence" }),
  ).toBeVisible();
  await page.waitForTimeout(1000);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth + 1,
  );
  expect(overflow).toBe(false);
  await page.screenshot({
    path: "../artifacts/screenshots/mobile.png",
    fullPage: true,
  });
});
