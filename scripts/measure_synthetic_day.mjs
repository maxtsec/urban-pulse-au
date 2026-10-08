import { execFileSync } from "node:child_process";
import { chromium } from "../apps/web/node_modules/@playwright/test/index.mjs";
import { mkdirSync, writeFileSync } from "node:fs";
const origin = process.env.URBANPULSE_SERVING_URL ?? "http://127.0.0.1:5178";
if (new URL(origin).hostname !== "127.0.0.1")
  throw new Error("Use a loopback compiled preview");
const outputDir = ".local/synthetic-day";
mkdirSync(outputDir, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ["--enable-unsafe-swiftshader"],
});
const sourceCommit = execFileSync("git", ["rev-parse", "HEAD"], {
  encoding: "utf8",
}).trim();
const dirty = Boolean(
  execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" }).trim(),
);
const output = [];
try {
  for (const [name, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 390, 844],
  ]) {
    const page = await browser.newPage({
      viewport: { width, height },
      reducedMotion: "no-preference",
    });
    const requests = [];
    page.on("response", (r) => requests.push(r.url()));
    await page.goto(origin + "/?experience=day");
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector("[data-models]")?.getAttribute("data-models") ===
        "ready",
    );
    await page.getByLabel("History time").fill(String(9 * 3600000));
    await page.getByRole("button", { name: "Play demo" }).click();
    const sample = await page.evaluate(
      () =>
        new Promise((resolve) => {
          const samples = [];
          let start = 0,
            last = 0;
          function frame(now) {
            if (!start) start = now;
            if (last) samples.push(now - last);
            last = now;
            if (now - start < 5000) requestAnimationFrame(frame);
            else {
              samples.sort((a, b) => a - b);
              resolve({
                frames: samples.length,
                durationMs: now - start,
                p95RafMs: samples[Math.floor(samples.length * 0.95)],
                resources: performance
                  .getEntriesByType("resource")
                  .filter((r) => r.name.startsWith(location.origin))
                  .map((r) => ({
                    name: r.name.split("/").pop(),
                    encoded: r.encodedBodySize,
                    decoded: r.decodedBodySize,
                  })),
              });
            }
          }
          requestAnimationFrame(frame);
        }),
    );
    await page.getByRole("button", { name: "Pause demo" }).click();
    await page.getByLabel("History time").fill(String(9 * 3600000));
    await page.screenshot({
      path: outputDir + "/explorer-" + name + "-rain.png",
    });
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("HeapProfiler.collectGarbage");
    const heap = await cdp.send("Runtime.getHeapUsage");
    output.push({
      name,
      width,
      height,
      ...sample,
      heap,
      modelState: await page.getByTestId("map").getAttribute("data-models"),
    });
    await page.close();
  }
} finally {
  await browser.close();
}
writeFileSync(
  outputDir + "/measurement.json",
  JSON.stringify({ sourceCommit, dirty, samples: output }, null, 2),
);
console.log(
  JSON.stringify(
    output.map(({ resources, ...r }) => ({
      ...r,
      encodedBytes: resources.reduce((sum, v) => sum + v.encoded, 0),
    })),
  ),
);
