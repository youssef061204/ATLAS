import { expect, test } from "@playwright/test";
test.skip(
  !!process.env.CI && process.env.ATLAS_PUBLIC_TEST !== "true",
  "City integration needs the prepared public build or configured Python worker",
);

test("five actual city catalogs and aggregate observations remain truthful", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/cities");
  await expect(
    page.getByRole("heading", { name: "City intelligence", exact: true }),
  ).toBeVisible();
  const cities = page.getByRole("combobox", {
    name: "Select city",
    exact: true,
  });
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await cities.selectOption(city);
    await expect(
      page.getByRole("group", { name: "Official camera coordinates" }),
    ).toBeVisible();
    await expect(page.getByText("Not verified", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Visible object counts", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Show OSM corridor" }).click();
    await expect(
      page.getByRole("group", {
        name: "Imported OSM corridor and simulated signal states",
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Show camera coverage" }).click();
  }
  expect(errors).toEqual([]);
});

test("saved SUMO comparison scrubs actual paired traces and exposes decisions", async ({
  page,
}) => {
  const responsePromise = page.waitForResponse(
    (r) =>
      r.status() === 200 &&
      (r.url().endsWith("/api/operations/experiments") ||
        r.url().endsWith("/demo/cities/experiments.json")),
  );
  await page.goto("/studio");
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  const run = data.runs.find(
    (r: { city: string; policy: string }) =>
      r.city === "toronto" && r.policy === "risk_mpc",
  );
  await expect(
    page.getByRole("heading", { name: "Optimization studio", exact: true }),
  ).toBeVisible();
  const slider = page.getByRole("slider", { name: "Network replay timeline" });
  await expect(slider).toBeVisible();
  await slider.fill("20");
  await expect(
    page.getByText(`Replay time ${run.trace[20].t} s`, { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByText(`${run.metrics.mean_delay_s.toFixed(2)} s`, { exact: true })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Play recorded comparison" }).click();
  await expect.poll(() => slider.inputValue()).not.toBe("20");
  await page.getByRole("button", { name: "Pause replay" }).click();
  await page
    .getByRole("combobox", { name: "Baseline controller" })
    .selectOption("max_pressure");
  await expect(
    page.getByRole("heading", { name: "Max-pressure", exact: true }),
  ).toBeVisible();
});

test("pilot exports real evidence and responsive pages have no runtime errors", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/pilot");
  await expect(
    page.getByRole("heading", { name: "Municipal pilot studio", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("spinbutton", { name: "Vehicles per day", exact: true })
    .fill("2000");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export pilot assessment" }).click();
  expect((await download).suggestedFilename()).toBe(
    "atlas-toronto-pilot-assessment.json",
  );
  for (const route of ["/cities", "/studio", "/pilot"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 2,
      ),
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test("local operator executes two real jobs and selects their new replay", async ({
  page,
}) => {
  test.skip(
    !process.env.ATLAS_TEST_OPERATOR_KEY,
    "Requires an explicitly configured authenticated local worker",
  );
  await page.goto("/studio");
  await page
    .getByLabel("Operator key")
    .fill(process.env.ATLAS_TEST_OPERATOR_KEY!);
  await page.getByLabel("Simulation seed").fill("19005");
  await page.getByRole("button", { name: "Run new paired simulation" }).click();
  await expect(
    page.getByText(
      "Two new simulations completed. Their actual outputs are selected in the replay.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.getByText(/Paired seed 19005/)).toBeVisible();
  await expect(page.getByLabel("Operator key")).toHaveValue("");
});
