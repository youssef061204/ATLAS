import { expect, test } from "@playwright/test";

test("3D comparison, track inspection, camera controls and exact frame stepping", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/reality");
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect(page.locator("canvas")).toBeVisible();
  const picker = page.getByLabel("Select tracked vehicle", { exact: true });
  const identity = await picker.locator("option").nth(1).getAttribute("value");
  expect(identity).toBeTruthy();
  await picker.selectOption(identity!);
  await expect(
    page.getByLabel("Vehicle correspondence inspector"),
  ).toContainText("Observed CV:");
  await page.getByRole("button", { name: "Follow", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Follow", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Top down", exact: true }).click();
  await page.getByRole("button", { name: "Fit / reset", exact: true }).click();
  await page
    .getByRole("button", { name: "Next video frame", exact: true })
    .click();
  const media = page
    .getByRole("region", { name: "Real traffic video", exact: true })
    .locator("video");
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeCloseTo(600.1, 2);
  expect(
    await media.evaluate((video) => (video as HTMLVideoElement).paused),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Previous video frame", exact: true })
    .click();
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeCloseTo(600, 2);
  await page
    .getByLabel("Vehicle layers", { exact: true })
    .selectOption("observed");
  await page.getByLabel("Survey markings", { exact: true }).uncheck();
  await page.getByLabel("2005 orthophoto", { exact: true }).uncheck();
  await page.getByRole("button", { name: "2D map", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /Actual SUMO reconstruction/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("both historical traffic videos remain accessible and playable", async ({
  page,
}) => {
  test.skip(
    !process.env.ATLAS_PUBLIC_DEMO,
    "Original cached video requires the public demo configuration",
  );
  await page.goto("/reality");
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", {
      name: "Lankershim / full continuous recording",
      exact: true,
    })
    .click();
  await expect
    .poll(() =>
      page
        .locator("video")
        .evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeCloseTo(0, 1);
  await page
    .getByRole("link", {
      name: "Original traffic video / CV workspace",
      exact: true,
    })
    .click();
  const media = page.locator("video");
  await expect(media).toBeVisible();
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).readyState),
    )
    .toBeGreaterThanOrEqual(2);
  await media.evaluate((video) => (video as HTMLVideoElement).play());
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeGreaterThan(0.1);
});

test("frozen experiment reports expose held-out failures and actual live-source scope", async ({
  page,
}) => {
  await page.goto("/reality");
  const report = page.getByRole("region", {
    name: "Inspect the evidence behind the reconstruction.",
  });
  await expect(
    report.getByText("Acceptance not met", { exact: true }),
  ).toBeVisible();
  await report
    .getByRole("button", { name: "Cross-camera", exact: true })
    .click();
  await expect(report.getByRole("table")).toContainText("0.1649");
  await expect(report.getByRole("table")).toContainText("56,337");
  await report
    .getByRole("button", { name: "Independent site", exact: true })
    .click();
  await expect(report.getByRole("table")).toContainText("0.4901");
  await expect(report.getByRole("table")).toContainText("fresh tracks");
  await report
    .getByRole("button", { name: "Live ingestion", exact: true })
    .click();
  await expect(
    report.getByRole("heading", {
      name: "Daytime traffic video, processed frame by frame.",
    }),
  ).toBeVisible();
  await expect(report).toContainText("258");
  await expect(report).toContainText("5 identity resets");
  await expect(report).toContainText("Archived nighttime trial");
  await report
    .getByRole("button", { name: "Video forecasting", exact: true })
    .click();
  await expect(report.getByRole("table")).toContainText("1.55");
  await expect(report).toContainText("only eight five-minute test origins");
});

test("unavailable experiment artifacts withhold their metrics", async ({
  page,
}) => {
  await page.route("**/demo/reality/v7/research.json", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.goto("/reality");
  const report = page.getByRole("region", {
    name: "Inspect the evidence behind the reconstruction.",
  });
  await expect(report.getByRole("alert")).toContainText(
    "No replacement metrics",
  );
  await expect(report.getByText("13.64 m", { exact: true })).toHaveCount(0);
});
