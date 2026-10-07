// Opt-in gzip/throttling and separate sampled-heap experiments.
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { createRequire } from "node:module";
import { parseArgs } from "node:util";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { startAssetServer } from "./tram_chunk_http.mjs";
import { loadArea } from "./tram_chunk_loader.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const { values } = parseArgs({
  options: {
    assets: { type: "string" },
    output: { type: "string" },
    "web-root": { type: "string", default: join(root, "apps/web") },
    repeats: { type: "string", default: "3" },
    mode: { type: "string", default: "transport" },
  },
});
const repeats = Number(values.repeats);
if (
  !values.assets ||
  !values.output ||
  !["transport", "memory"].includes(values.mode) ||
  !Number.isInteger(repeats) ||
  repeats < 1 ||
  repeats > 10
)
  throw new Error("Invalid experiment arguments");
const webRoot = resolve(values["web-root"]);
if (
  !(await readFile(join(webRoot, "package-lock.json"))).equals(
    await readFile(join(root, "apps/web/package-lock.json")),
  )
)
  throw new Error("Reused web dependencies must have the same lockfile");
const { chromium } = createRequire(join(webRoot, "package.json"))(
  "@playwright/test",
);
const directory = resolve(values.assets);
const discoveryBytes = await readFile(join(directory, "comparison.json"));
const discovery = JSON.parse(discoveryBytes);
const assets = new Map();
for (const policy of ["shape", "route"]) {
  for (const kind of ["areas", "objects"]) {
    for (const entry of await readdir(join(directory, policy, kind), {
      withFileTypes: true,
    })) {
      if (!entry.isFile() || !/^[a-f0-9]{64}\.json$/.test(entry.name))
        throw new Error("Unexpected generated asset");
      assets.set(
        `/${policy}/${kind}/${entry.name}`,
        await readFile(join(directory, policy, kind, entry.name)),
      );
    }
  }
}
const profiles =
  values.mode === "transport"
    ? [
        { name: "gzip-local", latency: 0, downloadThroughput: -1 },
        { name: "gzip-1mbps-50ms", latency: 50, downloadThroughput: 125000 },
      ]
    : [{ name: "gzip-heap", latency: 0, downloadThroughput: -1 }];
const server = await startAssetServer(assets);
let browser;
const measurements = [];
try {
  browser = await chromium.launch();
  for (const profile of profiles) {
    const areas = Object.keys(discovery.required_shapes).sort();
    for (let repeat = 0; repeat < repeats; repeat++) {
      // Alternate layout order between repeats to reduce systematic warm-up bias.
      for (const policy of repeat % 2
        ? ["route", "shape"]
        : ["shape", "route"]) {
        for (const order of [areas, [...areas].reverse()]) {
          const context = await browser.newContext();
          try {
            const page = await context.newPage();
            const cdp = await context.newCDPSession(page);
            await cdp.send("Network.enable");
            await cdp.send("Network.emulateNetworkConditions", {
              offline: false,
              latency: profile.latency,
              downloadThroughput: profile.downloadThroughput,
              uploadThroughput: -1,
            });
            await page.goto(server.origin);
            for (const [step, area] of order.entries()) {
              server.reset();
              const samples = [];
              let sampling = false,
                sampler,
                before;
              if (values.mode === "memory") {
                await page.evaluate(() => {
                  globalThis.__tramBenchmarkGeometry = null;
                });
                await cdp.send("HeapProfiler.collectGarbage");
                before = await cdp.send("Runtime.getHeapUsage");
                sampling = true;
                sampler = (async () => {
                  while (sampling) {
                    samples.push(await cdp.send("Runtime.getHeapUsage"));
                    await new Promise((done) => setTimeout(done, 20));
                  }
                })();
              }
              let result;
              try {
                result = await page.evaluate(loadArea, {
                  policy,
                  manifest: discovery.layouts[policy][area].manifest,
                  expected: discovery.required_shapes[area],
                  retain: values.mode === "memory",
                });
              } finally {
                sampling = false;
                await sampler;
              }
              let heap;
              if (values.mode === "memory") {
                samples.push(await cdp.send("Runtime.getHeapUsage"));
                await cdp.send("HeapProfiler.collectGarbage");
                const retained = await cdp.send("Runtime.getHeapUsage");
                await page.evaluate(() => {
                  globalThis.__tramBenchmarkGeometry = null;
                });
                await cdp.send("HeapProfiler.collectGarbage");
                const released = await cdp.send("Runtime.getHeapUsage");
                heap = {
                  before,
                  retained,
                  released,
                  samples,
                  sampled_max_used_bytes: Math.max(
                    ...samples.map((s) => s.usedSize),
                  ),
                  retained_delta_bytes: retained.usedSize - before.usedSize,
                };
              }
              const network = server.requests;
              if (network.some((r) => r.encoding !== "gzip"))
                throw new Error("Expected gzip on every network asset");
              measurements.push({
                profile: profile.name,
                policy,
                order,
                repeat,
                area,
                cache: step === 0 ? "cold" : "after-other-area",
                ...result,
                ...(heap ? { heap } : {}),
                network_requests: network.length,
                network_wire_bytes: network.reduce(
                  (n, r) => n + r.wire_bytes,
                  0,
                ),
                network_decoded_bytes: network.reduce(
                  (n, r) => n + r.decoded_bytes,
                  0,
                ),
              });
            }
          } finally {
            await context.close();
          }
        }
      }
    }
  }
  for (const area of Object.keys(discovery.required_shapes)) {
    if (
      new Set(
        measurements
          .filter((r) => r.area === area)
          .map((r) => r.geometry_sha256),
      ).size !== 1
    )
      throw new Error("Geometry differs across encodings/layouts/cache states");
  }
  const sourceFiles = {};
  for (const name of [
    "scripts/benchmark_tram_transport.mjs",
    "scripts/tram_chunk_http.mjs",
    "scripts/tram_chunk_loader.mjs",
    "scripts/build_tram_chunk_comparison.py",
    "scripts/build_tram_fixture.py",
    "scripts/build_tram_shape_pool.py",
    "apps/web/package-lock.json",
  ])
    sourceFiles[name] = createHash("sha256")
      .update(await readFile(join(root, name)))
      .digest("hex");
  const report = {
    schema_version: "tram-transport-experiment-v1",
    mode: values.mode,
    node: process.version,
    zlib: process.versions.zlib,
    chromium: browser.version(),
    source_commit: execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: root,
      encoding: "utf8",
    }).trim(),
    dirty: !!execFileSync("git", ["status", "--porcelain"], {
      cwd: root,
      encoding: "utf8",
    }).trim(),
    source_files_sha256: sourceFiles,
    source_revision: discovery.source_revision,
    comparison_sha256: createHash("sha256")
      .update(discoveryBytes)
      .digest("hex"),
    protocol:
      "loopback HTTP/1.1; gzip level 6; CDP aggregate download throttle",
    memory_scope:
      "Separate run: sampled V8 usedSize at >=20 ms intervals; post-GC retained selected geometry. Not renderer RSS, GPU memory or an exact peak. Memory-run elapsed times are instrumented.",
    profiles,
    repeats,
    concurrency: 6,
    gzip_level: 6,
    measurements,
  };
  await writeFile(
    resolve(values.output),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(
    JSON.stringify({ mode: values.mode, loads: measurements.length }),
  );
} finally {
  try {
    await browser?.close();
  } finally {
    await server.close();
  }
}
