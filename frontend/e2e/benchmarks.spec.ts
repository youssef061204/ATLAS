import { expect, test } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

test("benchmark-fixture renders committed real artifacts and preserves negative results", async ({
  page,
}) => {
  const directory = path.resolve(process.cwd(), "../artifacts/benchmarks");
  const real_world = Object.fromEntries(
    readdirSync(directory)
      .filter((name) => name.endsWith(".json"))
      .map((name) => [
        name.slice(0, -5),
        JSON.parse(readFileSync(path.join(directory, name), "utf8")),
      ]),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/benchmarks", (route) =>
    route.fulfill({ json: { real_world } }),
  );
  await page.route("**/api/benchmarks/improved_signal_control", (route) =>
    route.fulfill({ json: real_world.improved_signal_control }),
  );
  await page.route("**/api/benchmarks/signal_control_ablations", (route) =>
    route.fulfill({ json: real_world.signal_control_ablations }),
  );
  await page.goto("/benchmarks");
  await expect(
    page.getByRole("heading", { name: "Real-world results", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Controlled / synthetic results",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(real_world.real_detection.metrics.map50.toFixed(3), {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(real_world.real_tracking.metrics.IDF1.toFixed(3), {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("A negative reduction means higher delay", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "15 MIN", exact: true }).click();
  await expect(
    page.getByText(
      real_world.real_forecasting.metrics.horizons[
        "15"
      ].atlas_gradient_boosting.mae.toFixed(3),
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.locator('a[href$="/api/benchmarks/real_detection"]'),
  ).toBeVisible();
  expect(errors).toEqual([]);
  await expect(
    page
      .getByRole("table", { name: "Held-out signal-control metrics" })
      .locator("tbody tr"),
  ).toHaveCount(4);
});

test("benchmark-fixture handles absent real data without inventing scores", async ({
  page,
}) => {
  await page.route("**/api/benchmarks", (route) => route.fulfill({ json: {} }));
  await page.goto("/benchmarks");
  await expect(
    page.getByRole("heading", {
      name: "Real-data artifacts are not installed.",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("UA-DETRAC / PRETRAINED DETECTION", { exact: true }),
  ).toHaveCount(0);
});
