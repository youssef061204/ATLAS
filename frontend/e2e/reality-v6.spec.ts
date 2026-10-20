import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("real-video replay synchronizes actual footage, CV boxes and native SUMO", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/reality");
  await expect(
    page.getByRole("heading", { name: "Real video. Measured reconstruction." }),
  ).toBeVisible();
  const media = page.locator("video");
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).readyState),
    )
    .toBeGreaterThanOrEqual(2);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeCloseTo(600, 0);
  const chunk = await page.request.get("/demo/reality/v7/replay-0600.json");
  expect(chunk.ok()).toBeTruthy();
  const data = await chunk.json();
  await expect(page.locator("svg[viewBox='0 0 640 480'] rect")).toHaveCount(
    data.frames[0].filter((box: unknown[]) => !box[7]).length,
  );
  await expect(
    page.getByRole("region", { name: "Synchronized SUMO reconstruction" }),
  ).toContainText(`${data.simulation["600"].length} actual SUMO vehicles`);
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeGreaterThan(600.4);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  const paused = await media.evaluate(
    (video) => (video as HTMLVideoElement).currentTime,
  );
  await page.waitForTimeout(250);
  expect(
    await media.evaluate((video) => (video as HTMLVideoElement).currentTime),
  ).toBeCloseTo(paused, 1);
  await page
    .getByRole("slider", { name: "Shared replay timeline" })
    .fill("1050.4");
  await expect
    .poll(() =>
      media.evaluate((video) => (video as HTMLVideoElement).currentTime),
    )
    .toBeCloseTo(1050.4, 1);
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  await expect(page.getByLabel("Playback time")).toContainText("17:30");
  await expect(
    page.getByText(
      "This baseline has not established acceptable physical fidelity.",
      { exact: false },
    ),
  ).toBeVisible();
  await page
    .getByText("ATLAS 6 archived validation and failed experiments", {
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Association regressed and is not promoted.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("471 of 720 planned seconds", { exact: false }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("real-video evidence remains usable on mobile and passes accessibility", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/reality");
  await expect(
    page.getByRole("button", { name: "Play", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    ),
  ).toBeLessThanOrEqual(2);
  expect(await new AxeBuilder({ page }).analyze()).toMatchObject({
    violations: [],
  });
  await expect(
    page.getByRole("link", { name: "Inspect independent CV evaluation" }),
  ).toHaveAttribute("href", "/demo/reality/v7/cv-validation.json");
  await expect(
    page.getByText("No field-live processing runs on this public deployment.", {
      exact: false,
    }),
  ).toBeVisible();
});

test("missing real-video evidence never displays fabricated metrics", async ({
  page,
}) => {
  await page.route("**/demo/reality/v7/manifest.json", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.goto("/reality");
  await expect(
    page.getByRole("alert").filter({ hasText: "Replay asset failed" }),
  ).toContainText("Replay asset failed (503)");
  await expect(
    page.getByRole("button", { name: "Retry loading" }),
  ).toBeVisible();
  await expect(
    page.getByText("SIMULATION COUNT MAE", { exact: true }),
  ).toHaveCount(0);
});
