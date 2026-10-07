// Loopback-only asset server for controlled experiments, not production serving.
import { createServer } from "node:http";
import { gzipSync } from "node:zlib";

export function acceptsGzip(value = "") {
  return value.split(",").some((part) => {
    const [name, ...params] = part.trim().split(";");
    if (name.trim().toLowerCase() !== "gzip") return false;
    const quality = params.find((p) => p.trim().startsWith("q="));
    return quality === undefined || Number(quality.trim().slice(2)) > 0;
  });
}

export async function startAssetServer(assets) {
  const compressed = new Map(
    [...assets].map(([path, raw]) => [path, gzipSync(raw, { level: 6 })]),
  );
  let requests = [];
  const server = createServer((req, res) => {
    if (req.url === "/") {
      res.writeHead(200, {
        "Content-Type": "text/html",
        "Cache-Control": "no-store",
      });
      res.end("<!doctype html><title>Local transport experiment</title>");
      return;
    }
    const raw = assets.get(req.url);
    if (!raw) {
      res.writeHead(404);
      res.end();
      return;
    }
    const gzip = acceptsGzip(req.headers["accept-encoding"]);
    const body = gzip ? compressed.get(req.url) : raw;
    requests.push({
      path: req.url,
      encoding: gzip ? "gzip" : "identity",
      wire_bytes: body.length,
      decoded_bytes: raw.length,
    });
    res.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Length": body.length,
      ...(gzip ? { "Content-Encoding": "gzip" } : {}),
      Vary: "Accept-Encoding",
      "Cache-Control": "public, max-age=31536000, immutable",
    });
    res.end(body);
  });
  await new Promise((done, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", done);
  });
  return {
    origin: `http://127.0.0.1:${server.address().port}`,
    reset() {
      requests = [];
    },
    get requests() {
      return [...requests];
    },
    sizes: Object.fromEntries(
      [...assets].map(([path, raw]) => [
        path,
        { decoded_bytes: raw.length, gzip_bytes: compressed.get(path).length },
      ]),
    ),
    async close() {
      server.closeAllConnections();
      await new Promise((done) => server.close(done));
    },
  };
}
