import { expect, test } from "@playwright/test";

test.describe("public-demo", () => {
  test.skip(
    !process.env.ATLAS_PUBLIC_DEMO,
    "Requires the built precomputed-demo environment",
  );
  test("all public navigation and assets load on desktop and mobile", async ({
    page,
  }) => {
    const errors: string[] = [];
    const failures: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 400)
        failures.push(
          `${response.status()} ${new URL(response.url()).pathname}`,
        );
    });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      for (const route of [
        "/",
        "/analytics",
        "/safety",
        "/forecast",
        "/optimization",
        "/benchmarks",
        "/about",
      ]) {
        const response = await page.goto(route);
        expect(response?.status()).toBe(200);
        await expect(page.locator("main")).toBeVisible();
        await page.waitForTimeout(350);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
        ).toBe(true);
      }
    }
    expect(errors).toEqual([]);
    expect(failures).toEqual([]);
  });
  test("real replay and twin load without local API dependencies", async ({
    page,
  }) => {
    const errors: string[] = [];
    const localRequests: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (/localhost:8000|127\.0\.0\.1:8000/.test(request.url()))
        localRequests.push(request.url());
    });
    await page.goto("/");
    await expect(page.getByText("0.898", { exact: true })).toBeVisible();
    await page
      .getByRole("link", { name: "Launch Demo", exact: true })
      .first()
      .click();
    await expect(
      page.getByText("PRECOMPUTED REAL CV DEMO", { exact: true }),
    ).toBeVisible();
    await expect(page.locator("canvas")).toBeVisible();
    await expect
      .poll(() =>
        page.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime),
      )
      .toBeGreaterThan(0.5);
    await page.getByRole("button", { name: "Pause playback" }).click();
    await page.getByRole("slider", { name: "Video timeline" }).fill("3");
    await page.locator(".cv-overlay g").first().click();
    await expect(page.locator(".object-title")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Import footage" }),
    ).toBeDisabled();
    expect(errors).toEqual([]);
    expect(localRequests).toEqual([]);
  });
  test("forecast and precomputed control remain interactive", async ({
    page,
    request,
  }) => {
    await page.goto("/forecast");
    await expect(page.getByText("2.490", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "15 MIN", exact: true }).click();
    await expect(
      page
        .getByRole("region", { name: "Real-world results" })
        .getByText("3.214", { exact: true }),
    ).toBeVisible();
    await page.goto("/optimization");
    await expect(
      page.getByText("ALL THREE POLICIES / FINAL METRICS"),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Replay precomputed comparison" })
      .click();
    await expect(
      page.getByRole("button", { name: "Pause simulation" }),
    ).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(3);
    expect((await request.post("/api/videos", { data: {} })).status()).toBe(
      409,
    );
    expect(
      (
        await request.post("/api/simulations", {
          data: { seed: 43, duration: 300, demand: [0.38, 0.12, 0.32, 0.1] },
        })
      ).status(),
    ).toBe(409);
  });
  test("real benchmark links and narrow layout work", async ({
    page,
    request,
  }) => {
    await page.goto("/benchmarks");
    await expect(page.getByText("0.898", { exact: true })).toBeVisible();
    await expect(
      page.getByText("A negative reduction means higher delay", {
        exact: false,
      }),
    ).toBeVisible();
    const raw = await request.get("/api/benchmarks/real_detection");
    expect(raw.status()).toBe(200);
    expect((await raw.json()).data_provenance).toBe("real");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  });
});
