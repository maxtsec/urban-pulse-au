import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { get } from "node:http";
import { gunzipSync } from "node:zlib";
import { acceptsGzip, startAssetServer } from "./tram_chunk_http.mjs";
import { loadArea } from "./tram_chunk_loader.mjs";

function reference(value, kind = "objects") {
  const raw = Buffer.from(JSON.stringify(value));
  const sha256 = createHash("sha256").update(raw).digest("hex");
  return {
    raw,
    ref: { path: `${kind}/${sha256}.json`, sha256, bytes: raw.length },
  };
}

function rawGet(url, encoding) {
  return new Promise((resolve, reject) => {
    get(url, { headers: { "Accept-Encoding": encoding } }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("error", reject);
      response.on("end", () =>
        resolve({
          status: response.statusCode,
          headers: response.headers,
          raw: Buffer.concat(chunks),
        }),
      );
    }).on("error", reject);
  });
}

test("gzip negotiation respects an explicit zero quality", () => {
  assert.equal(acceptsGzip("br, gzip;q=0, deflate"), false);
  assert.equal(acceptsGzip("br, gzip;q=0.5"), true);
  assert.equal(acceptsGzip("gzip"), true);
  assert.equal(acceptsGzip(), false);
});

test("server serves compressed bytes and preserves decoded integrity and cache metadata", async () => {
  const { raw, ref } = reference({ content: "geometry".repeat(1000) });
  const path = `/shape/${ref.path}`;
  const server = await startAssetServer(new Map([[path, raw]]));
  try {
    const gzip = await rawGet(server.origin + path, "gzip");
    assert.equal(gzip.status, 200);
    assert.equal(gzip.headers["content-encoding"], "gzip");
    assert.equal(gzip.headers.vary, "Accept-Encoding");
    assert.match(gzip.headers["cache-control"], /immutable/);
    assert.deepEqual(gunzipSync(gzip.raw), raw);
    assert.ok(gzip.raw.length < raw.length);
    assert.equal(Number(gzip.headers["content-length"]), gzip.raw.length);
    assert.equal(server.requests[0].wire_bytes, gzip.raw.length);
    const identity = await rawGet(server.origin + path, "gzip;q=0");
    assert.equal(identity.headers["content-encoding"], undefined);
    assert.deepEqual(identity.raw, raw);
    const decoded = await fetch(server.origin + path);
    assert.deepEqual(Buffer.from(await decoded.arrayBuffer()), raw);
    assert.equal((await rawGet(server.origin + "/.env", "gzip")).status, 404);
    server.reset();
    assert.deepEqual(server.requests, []);
  } finally {
    await server.close();
  }
});

function setup(
  t,
  { policy = "route", missing = false, conflict = false } = {},
) {
  const feature = {
    properties: { shape_id: "a" },
    geometry: {
      coordinates: [
        [1, 2],
        [3, 4],
      ],
    },
  };
  const other = {
    properties: { shape_id: "b" },
    geometry: {
      coordinates: [
        [4, 5],
        [6, 7],
      ],
    },
  };
  const values =
    policy === "route"
      ? [
          { features: [feature, other] },
          { features: [conflict ? { ...feature, geometry: null } : feature] },
        ]
      : [{ feature }];
  const objects = values.map((v) => reference(v));
  const refs = Object.fromEntries(objects.map((o, i) => [String(i), o.ref]));
  const manifest = reference(
    policy === "route" ? { objects: refs } : { shapes: refs },
    "areas",
  );
  const assets = new Map(
    [manifest, ...objects].map((o) => [`/${policy}/${o.ref.path}`, o.raw]),
  );
  t.mock.method(globalThis, "fetch", async (url) => {
    const raw = assets.get(url);
    return new Response(raw ?? "", { status: raw ? 200 : 404 });
  });
  return {
    assets,
    objects,
    args: {
      policy,
      manifest: manifest.ref,
      expected: missing ? ["missing"] : ["a"],
    },
  };
}

test("route/shape loaders select identical geometry despite route duplicates and extras", async (t) => {
  const route = setup(t);
  const result = await loadArea({ ...route.args, retain: true });
  assert.equal(result.extra_shapes, 1);
  assert.equal(globalThis.__tramBenchmarkGeometry.length, 1);
  assert.equal(globalThis.__tramBenchmarkGeometry[0].properties.shape_id, "a");
  delete globalThis.__tramBenchmarkGeometry;
  t.mock.restoreAll();
  const shape = setup(t, { policy: "shape" });
  assert.equal(
    (await loadArea(shape.args)).geometry_sha256,
    result.geometry_sha256,
  );
});

test("corruption cannot produce a successful measurement", async (t) => {
  const { assets, objects, args } = setup(t);
  assets.set(`/route/${objects[0].ref.path}`, Buffer.from("{}"));
  await assert.rejects(loadArea(args), /integrity failure/);
});

test("missing object fails with its HTTP status", async (t) => {
  const { assets, objects, args } = setup(t);
  assets.delete(`/route/${objects[0].ref.path}`);
  await assert.rejects(loadArea(args), /HTTP 404/);
});

test("conflicting duplicate shape fails rather than selecting the last route", async (t) => {
  const { args } = setup(t, { conflict: true });
  await assert.rejects(loadArea(args), /Conflicting shape/);
});

test("missing required geometry and off-origin reference are rejected", async (t) => {
  const { args } = setup(t, { missing: true });
  await assert.rejects(loadArea(args), /Missing required shape/);
  args.manifest.path = "https://example.invalid/object";
  await assert.rejects(loadArea(args), /Invalid reference path/);
});
