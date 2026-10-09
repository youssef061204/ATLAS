import { expect, test } from "@playwright/test";

test.skip(
  !!process.env.CI && process.env.ATLAS_PUBLIC_TEST !== "true",
  "Requires prepared evidence and an actual public or native server",
);

test("official observation follows its actual experiment into replay and pilot", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/twin");
  await expect(
    page.getByRole("heading", {
      name: "Traffic intelligence loop",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("4", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText(/Historical counts are kept separate/),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Watch synchronized comparison" })
    .click();
  await expect(page.getByText(/Paired seed 21001/)).toBeVisible();
  await page.getByRole("slider", { name: "Network replay timeline" }).fill("5");
  expect(
    await page
      .getByRole("img", { name: "Actual simulated vehicle positions" })
      .first()
      .locator("circle")
      .count(),
  ).toBeGreaterThan(0);
  await expect(
    page.getByText("21.01 s", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("slider", { name: "Network replay timeline" })
    .fill("15");
  await expect(
    page.getByText("Replay time 75 s", { exact: true }),
  ).toBeVisible();
  await page.goto("/twin");
  await page.getByRole("link", { name: "Build a pilot assessment" }).click();
  await expect(page.getByText(/Frozen ATLAS MPC: 26.18 s/)).toBeVisible();
  await expect(
    page.getByText(/single paired run has no estimated uncertainty interval/),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export pilot assessment" }).click();
  expect((await download).suggestedFilename()).toBe(
    "atlas-toronto-pilot-assessment.json",
  );
  expect(errors).toEqual([]);
});

test("laboratory reports evaluated alternatives and mobile routes remain usable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/laboratory");
  await expect(
    page.getByRole("table", { name: "Forecast model evaluation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "2.438 mph", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Detector candidate comparison" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "97", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Crossing evaluation case" })
    .selectOption("17");
  await page
    .getByRole("combobox", { name: "Laboratory forecast horizon" })
    .selectOption("30");
  await page
    .getByRole("combobox", { name: "Forecast preview sensor" })
    .selectOption({ index: 1 });
  await expect(
    page.getByText(/Shared historical ATLAS test period/),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/cities", "/twin", "/studio", "/laboratory", "/pilot"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
    ).toBeTruthy();
  }
  expect(errors).toEqual([]);
});

test("authorized operator launches an actual observation-conditioned pair", async ({
  page,
}) => {
  test.skip(
    !process.env.ATLAS_TEST_OPERATOR_KEY,
    "Needs an authenticated native SUMO worker",
  );
  await page.goto("/twin");
  await page
    .getByLabel("Intelligence operator key")
    .fill(process.env.ATLAS_TEST_OPERATOR_KEY!);
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Optimize Traffic", exact: true })
    .click();
  await expect(
    page.getByText(
      "Both simulations completed using identical observation-conditioned demand.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.getByLabel("Intelligence operator key")).toHaveValue("");
  await page
    .getByRole("link", { name: "Watch synchronized comparison" })
    .click();
  await expect(page.getByText(/Paired seed 21002/)).toBeVisible();
});

test("changing cities never substitutes another source's measured counts", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/twin");
  await expect(
    page.getByRole("heading", { name: "Actual completed counterfactual" }),
  ).toBeVisible();
  await page
    .getByLabel("Intelligence city", { exact: true })
    .selectOption("london");
  await expect(
    page.getByRole("heading", { name: "Actual completed counterfactual" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Historical counts are kept separate/),
  ).toHaveCount(0);
  const camera = page.getByLabel("Intelligence camera");
  const options = await camera.locator("option").all();
  await camera.selectOption((await options.at(-1)!.getAttribute("value"))!);
  await expect(
    page.getByText(/No processed observation is selected/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Actual completed counterfactual" }),
  ).toHaveCount(0);
  await expect(
    page.getByText(/Historical counts are kept separate/),
  ).toHaveCount(0);
  await expect(page.getByLabel("Intelligence camera")).toHaveValue(/.+/);
  expect(errors).toEqual([]);
});

test("five-city recorded checks preserve zero-demand outcomes and real paired links", async ({
  page,
}) => {
  await page.goto("/twin?city=london");
  await expect(
    page.getByRole("heading", { name: "Actual completed counterfactual" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Watch synchronized comparison" })
    .click();
  await expect(page.getByText(/Paired seed 21102/)).toBeVisible();
  await expect(page.getByLabel("Simulation city")).toHaveValue("london");
  for (const city of ["seattle", "calgary"]) {
    await page.goto(`/twin?city=${city}`);
    await expect(
      page.getByText(/No motor vehicles were detected/),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Actual completed counterfactual" }),
    ).toHaveCount(0);
    await expect(
      page.getByText(/Historical counts are kept separate/),
    ).toHaveCount(0);
  }
});
