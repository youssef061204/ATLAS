import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

const root = path.resolve("..");
const read = async (name) =>
  JSON.parse(await fs.readFile(path.join(root, "data/ux-v4", name), "utf8"));
const baseline = await read("baseline.json");
const after = await read("after.json");
const accessibility = await read("accessibility.json");
if (
  accessibility.scans.some(
    (scan) =>
      scan.violations.length ||
      scan.horizontal_overflow_px > 2 ||
      scan.page_errors?.length,
  )
)
  throw new Error("Actual UX verification contains an unresolved failure");
if (
  after.results.some(
    (row) => row.page_errors.length || row.horizontal_overflow_px > 2,
  )
)
  throw new Error("Actual performance run contains a browser failure");
const sourceFiles = [
  "components/landing.tsx",
  "components/shell.tsx",
  "components/city-evidence-v4.tsx",
  "components/city-intelligence.tsx",
  "components/intelligence-workflow.tsx",
  "components/city-map.tsx",
  "components/network-studio.tsx",
  "components/pilot-studio.tsx",
  "components/ai-laboratory.tsx",
  "components/evidence-loading.tsx",
  "components/local-experiment.tsx",
  "lib/cities.ts",
  "lib/city-selection.ts",
  "app/globals.css",
  "scripts/measure-ux-v4.mjs",
  "scripts/verify-ux-v4.mjs",
];
const source = {};
for (const file of sourceFiles)
  source[file] = createHash("sha256")
    .update(await fs.readFile(file))
    .digest("hex");
const comparisons = baseline.results.map((before) => {
  const result = after.results.find(
    (row) => row.route === before.route && row.width === before.width,
  );
  if (!result) throw new Error("Missing matched route/viewport measurement");
  return {
    route: before.route,
    width: before.width,
    before_transfer_bytes: before.transfer_bytes,
    after_transfer_bytes: result.transfer_bytes,
    observed_transfer_reduction_percent:
      (100 * (before.transfer_bytes - result.transfer_bytes)) /
      before.transfer_bytes,
    before_lcp_ms: before.lcp_ms,
    after_lcp_ms: result.lcp_ms,
    before_task_ready_ms: before.task_ready_ms,
    after_task_ready_ms: result.task_ready_ms,
  };
});
const evidence = {
  version: "atlas-4",
  published_at: new Date().toISOString(),
  baseline_commit: "c0e78d187729d7912a035d4b45abc7fe8969c01b",
  scope:
    "Actual local production Next.js browser laboratory, same host, 1440px and 390px. One fresh context per route and viewport. Public precomputed real-data mode.",
  limitations: [
    "One sample per route/viewport; shared host CPU and remote font loading vary. Observed timing differences are not a statistically verified speedup.",
    "Local LCP and CLS observations are not field Core Web Vitals. Task-ready time is not TTI; event timings are not an aggregated INP score.",
    "120 requestAnimationFrame intervals measure available browser frame cadence after readiness, not end-to-end camera processing FPS.",
    "Heap values use Chromium performance.memory; browser process peak RSS and cross-browser memory are unmeasured.",
    "API timings are local recorded-file response observations, not a sustained backend SLA. Remote simulation startup is separately evaluated.",
    "Automated browser/accessibility checks do not constitute a human usability study or WCAG certification.",
  ],
  measured_source_sha256: source,
  baseline,
  after,
  comparisons,
  accessibility,
};
const target = path.join(root, "artifacts/cities/v4/ux-performance.json");
await fs.mkdir(path.dirname(target), { recursive: true });
await fs.writeFile(target, JSON.stringify(evidence, null, 2));
console.log(
  `Published ${comparisons.length} matched route/viewport samples and ${accessibility.scans.length} actual accessibility scans.`,
);
