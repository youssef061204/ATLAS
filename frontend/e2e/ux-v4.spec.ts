import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("pilot export retains all new paired seeds and an interval crossing zero", async ({
  page,
}) => {
  await page.goto("/pilot?city=calgary&cohort=atlas-4");
  await expect(page.getByText(/20 paired seeds/)).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export pilot assessment" }).click();
  const download = await pending;
  const report = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(report.evidence_cohort).toBe("atlas-4");
  expect(report.candidate.policy).toBe("network_mpc");
  expect(report.candidate.seeds).toBe(20);
  expect(report.field_validated).toBe(false);
  expect(report.paired_delay_ci95_s[0]).toBeLessThan(0);
  expect(report.paired_delay_ci95_s[1]).toBeGreaterThan(0);
  expect(
    new Set(report.simulation_inputs.map((row: { seed: number }) => row.seed))
      .size,
  ).toBe(20);
});

test("new held-out cohort exposes complete city summaries and actual first-seed replay", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await page.goto(`/studio?cohort=atlas-4&city=${city}`);
    await expect(page.getByLabel("Simulation city")).toHaveValue(city);
    await expect(
      page
        .getByRole("table", { name: "Held-out controller comparison" })
        .locator("tbody tr"),
    ).toHaveCount(6);
    await expect(
      page.getByText("Paired seed 43001", { exact: false }),
    ).toBeVisible();
    await expect(page.getByLabel("Network replay timeline")).toBeVisible();
    await page.getByLabel("Baseline controller").selectOption("max_pressure");
    await expect(
      page.getByRole("heading", { name: "Max-pressure", exact: true }),
    ).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("authenticated native operator explicitly executes cached MPC without promoting defaults", async ({
  page,
}) => {
  test.skip(
    !process.env.ATLAS_TEST_OPERATOR_KEY,
    "Needs an authenticated native SUMO worker",
  );
  await page.goto("/studio?cohort=atlas-4&city=toronto");
  await page
    .getByLabel("Operator key")
    .fill(process.env.ATLAS_TEST_OPERATOR_KEY!);
  await page.getByLabel("Simulation seed").fill("45005");
  await page.getByRole("button", { name: "Run new paired simulation" }).click();
  await expect(
    page.getByText(
      "Two new simulations completed. Their actual outputs are selected in the replay.",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.getByText(/Paired seed 45005/)).toBeVisible();
  await expect(page.getByLabel("Operator key")).toHaveValue("");
});

test.skip(
  !!process.env.CI && process.env.ATLAS_PUBLIC_TEST !== "true",
  "Needs prepared actual city evidence",
);

test("landing offers all five real corridors and preserves the selected city", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  const choices = page.getByRole("group", { name: "Choose a city" });
  await expect(choices.getByRole("button")).toHaveCount(5);
  await choices.getByRole("button", { name: /London/ }).click();
  await expect(choices.getByRole("button", { name: /London/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByRole("group", {
      name: "Imported OSM corridor and simulated signal states",
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Explore London", exact: true }).click();
  await expect(
    page.getByLabel("Intelligence city", { exact: true }),
  ).toHaveValue("london");
  await expect(page.getByLabel("Active city", { exact: true })).toHaveValue(
    "london",
  );
  await page
    .getByRole("link", { name: "Explore cities", exact: true })
    .first()
    .click();
  await expect(page.getByLabel("Select city", { exact: true })).toHaveValue(
    "london",
  );
  await page.reload();
  await expect(page.getByLabel("Select city", { exact: true })).toHaveValue(
    "london",
  );
  await page.goto("/pilot");
  await expect(page.getByLabel("Pilot city", { exact: true })).toHaveValue(
    "london",
  );
  expect(errors).toEqual([]);
});

test("each city exposes its real newest observation and completed paired replay", async ({
  page,
}) => {
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await page.goto(`/cities?city=${city}`);
    await expect(page.getByLabel("Select city", { exact: true })).toHaveValue(
      city,
    );
    await expect(
      page.getByRole("group", { name: "Official camera coordinates" }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Digital twin", exact: true }).click();
    await expect(
      page.getByLabel("Intelligence city", { exact: true }),
    ).toHaveValue(city);
    await expect(
      page.getByRole("region", { name: "Operator task guide" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Actual completed counterfactual" }),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Watch synchronized comparison" })
      .click();
    await expect(page.getByLabel("Simulation city")).toHaveValue(city);
    await expect(
      page.getByRole("slider", { name: "Network replay timeline" }),
    ).toBeVisible();
  }
});

test("URL overrides a stored city and mobile navigation remains usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/cities?city=london");
  await page.getByLabel("Select city", { exact: true }).selectOption("austin");
  await page.goto("/cities?city=calgary");
  await expect(page.getByLabel("Active city", { exact: true })).toHaveValue(
    "calgary",
  );
  await page.getByLabel("Active city", { exact: true }).selectOption("seattle");
  await expect(page.getByLabel("Select city", { exact: true })).toHaveValue(
    "seattle",
  );
  for (const route of [
    "/",
    "/cities?city=seattle",
    "/twin?city=seattle",
    "/studio?city=seattle",
    "/pilot?city=seattle",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
    ).toBe(true);
  }
});

test("historical city forecasting exposes actual model errors, regressions and dated values", async ({
  page,
}) => {
  for (const city of ["toronto", "london", "seattle", "austin", "calgary"]) {
    await page.goto(`/twin?city=${city}`);
    await page
      .getByText("Inspect historical city data & forecast validation", {
        exact: true,
      })
      .click();
    await expect(
      page
        .getByRole("table", {
          name: "City forecasting comparison",
          exact: true,
        })
        .locator("tbody tr"),
    ).toHaveCount(5);
    await expect(page.getByText(/not automatically promoted/)).toBeVisible();
    if (["toronto", "london"].includes(city))
      await expect(page.getByText(/candidate regresses/)).toBeVisible();
    await page
      .getByText("Inspect the actual dated forecast values", { exact: true })
      .click();
    await expect(
      page.getByRole("table", {
        name: "City historical forecast values",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByText("Leave-one-city-out generalization", { exact: true })
      .click();
    await expect(page.getByText(/0 target-city fit examples/)).toBeVisible();
  }
});
