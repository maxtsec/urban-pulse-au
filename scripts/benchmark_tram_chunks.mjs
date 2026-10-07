// Opt-in fetch/hash/parse experiment. No map rendering or production loader is installed.
import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { createRequire } from "node:module";
import { parseArgs } from "node:util";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const { values } = parseArgs({
  options: {
    assets: { type: "string" },
    output: { type: "string" },
    "web-root": { type: "string", default: join(root, "apps/web") },
    repeats: { type: "string", default: "3" },
  },
});
const repeats = Number(values.repeats);
if (
  !values.assets ||
  !values.output ||
  !Number.isInteger(repeats) ||
  repeats < 1 ||
  repeats > 10
)
  throw new Error(
    "Required: --assets DIR --output FILE; repeats must be 1..10",
  );
const { chromium } = createRequire(
  join(resolve(values["web-root"]), "package.json"),
)("@playwright/test");
const assets = new Map();
const directory = resolve(values.assets);
const discoveryBytes = await readFile(join(directory, "comparison.json"));
const discovery = JSON.parse(discoveryBytes);
for (const policy of ["shape", "route"]) {
  for (const kind of ["areas", "objects"]) {
    const folder = join(directory, policy, kind);
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      if (!entry.isFile() || !/^[a-f0-9]{64}\.json$/.test(entry.name))
        throw new Error("Unexpected generated asset");
      assets.set(
        `/${policy}/${kind}/${entry.name}`,
        await readFile(join(folder, entry.name)),
      );
    }
  }
}
let delay = 0;
let requests = [];
const server = createServer(async (req, res) => {
  if (req.url === "/") {
    res.writeHead(200, {
      "Content-Type": "text/html",
      "Cache-Control": "no-store",
    });
    res.end("<!doctype html><title>Local shape loading experiment</title>");
    return;
  }
  const raw = assets.get(req.url);
  if (!raw) {
    res.writeHead(404);
    res.end();
    return;
  }
  requests.push({ path: req.url, bytes: raw.length });
  await new Promise((done) => setTimeout(done, delay));
  res.writeHead(200, {
    "Content-Type": "application/json",
    "Content-Length": raw.length,
    "Cache-Control": "public, max-age=31536000, immutable",
  });
  res.end(raw);
});
await new Promise((done) => server.listen(0, "127.0.0.1", done));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch();
  const measurements = [];
  for (delay of [0, 50]) {
    for (const policy of ["shape", "route"]) {
      const areas = Object.keys(discovery.layouts[policy]).sort();
      for (const order of [areas, [...areas].reverse()]) {
        for (let repeat = 0; repeat < repeats; repeat++) {
          const context = await browser.newContext();
          try {
            const page = await context.newPage();
            page.setDefaultTimeout(60000);
            await page.goto(origin);
            for (const [step, area] of order.entries()) {
              requests = [];
              const result = await page.evaluate(
                async ({ policy, manifest, expected }) => {
                  const start = performance.now();
                  let hashMs = 0,
                    parseMs = 0,
                    bodyBytes = 0;
                  const read = async (ref) => {
                    if (!/^(areas|objects)\/[a-f0-9]{64}\.json$/.test(ref.path))
                      throw new Error("Invalid reference path");
                    const response = await fetch(`/${policy}/${ref.path}`, {
                      signal: AbortSignal.timeout(60000),
                    });
                    if (!response.ok)
                      throw new Error(`Asset HTTP ${response.status}`);
                    const buffer = await response.arrayBuffer();
                    bodyBytes += buffer.byteLength;
                    const beforeHash = performance.now();
                    const sha = Array.from(
                      new Uint8Array(
                        await crypto.subtle.digest("SHA-256", buffer),
                      ),
                      (byte) => byte.toString(16).padStart(2, "0"),
                    ).join("");
                    hashMs += performance.now() - beforeHash;
                    if (sha !== ref.sha256 || buffer.byteLength !== ref.bytes)
                      throw new Error("Asset integrity failure");
                    const beforeParse = performance.now();
                    const value = JSON.parse(
                      new TextDecoder("utf-8", { fatal: true }).decode(buffer),
                    );
                    parseMs += performance.now() - beforeParse;
                    return value;
                  };
                  const listing = await read(manifest);
                  const references = Object.values(
                    policy === "shape" ? listing.shapes : listing.objects,
                  );
                  const found = new Map();
                  let next = 0;
                  await Promise.all(
                    Array.from({ length: 6 }, async () => {
                      while (next < references.length) {
                        const value = await read(references[next++]);
                        for (const feature of policy === "shape"
                          ? [value.feature]
                          : value.features) {
                          const id = feature.properties.shape_id;
                          if (
                            found.has(id) &&
                            JSON.stringify(found.get(id)) !==
                              JSON.stringify(feature)
                          )
                            throw new Error("Conflicting shape across objects");
                          found.set(id, feature);
                        }
                      }
                    }),
                  );
                  if (expected.some((id) => !found.has(id)))
                    throw new Error("Missing required shape");
                  // This digest compares the actual retained geometry, not only ID counts.
                  const selected = expected.map((id) => found.get(id));
                  const bytes = new TextEncoder().encode(
                    JSON.stringify(selected),
                  );
                  const geometryHash = Array.from(
                    new Uint8Array(
                      await crypto.subtle.digest("SHA-256", bytes),
                    ),
                    (byte) => byte.toString(16).padStart(2, "0"),
                  ).join("");
                  return {
                    elapsed_ms: performance.now() - start,
                    hash_ms: hashMs,
                    parse_ms: parseMs,
                    body_bytes_read: bodyBytes,
                    required_shapes: expected.length,
                    extra_shapes: found.size - expected.length,
                    geometry_sha256: geometryHash,
                  };
                },
                {
                  policy,
                  manifest: discovery.layouts[policy][area].manifest,
                  expected: discovery.required_shapes[area],
                },
              );
              measurements.push({
                delay_ms: delay,
                policy,
                order,
                repeat,
                area,
                cache: step === 0 ? "cold" : "after-other-area",
                ...result,
                network_requests: requests.length,
                network_body_bytes: requests.reduce((n, r) => n + r.bytes, 0),
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
      throw new Error("Geometry differs across loading layouts/cache states");
  }
  const sourceFiles = {};
  for (const name of [
    "scripts/benchmark_tram_chunks.mjs",
    "scripts/build_tram_chunk_comparison.py",
    "scripts/build_tram_fixture.py",
    "scripts/build_tram_shape_pool.py",
    "apps/web/package-lock.json",
  ]) {
    sourceFiles[name] = createHash("sha256")
      .update(await readFile(join(root, name)))
      .digest("hex");
  }
  const report = {
    schema_version: "tram-browser-chunks-v1",
    node: process.version,
    chromium: browser.version(),
    source_revision: discovery.source_revision,
    comparison_sha256: createHash("sha256")
      .update(discoveryBytes)
      .digest("hex"),
    source_files_sha256: sourceFiles,
    source_commit: execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: root,
      encoding: "utf8",
    }).trim(),
    dirty: !!execFileSync("git", ["status", "--porcelain"], {
      cwd: root,
      encoding: "utf8",
    }).trim(),
    concurrency: 6,
    repeats,
    protocol: "loopback HTTP/1.1; uncompressed; no bandwidth throttle",
    timing:
      "wall load includes fetch, integrity, parsing, deduplication and selected-geometry hash; hash_ms is summed async duration, not CPU time",
    measurements,
  };
  await writeFile(
    resolve(values.output),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(
    JSON.stringify({ loads: measurements.length, chromium: report.chromium }),
  );
} finally {
  await browser?.close();
  server.closeAllConnections();
  await new Promise((done) => server.close(done));
}
