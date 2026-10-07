// Shared experiment loader; not imported by the application.
export async function loadArea({ policy, manifest, expected, retain = false }) {
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
    if (!response.ok) throw new Error(`Asset HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    bodyBytes += buffer.byteLength;
    const beforeHash = performance.now();
    const sha = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)),
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
            JSON.stringify(found.get(id)) !== JSON.stringify(feature)
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
  const bytes = new TextEncoder().encode(JSON.stringify(selected));
  const geometryHash = Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");
  if (retain) globalThis.__tramBenchmarkGeometry = selected;
  return {
    elapsed_ms: performance.now() - start,
    hash_ms: hashMs,
    parse_ms: parseMs,
    body_bytes_read: bodyBytes,
    required_shapes: expected.length,
    extra_shapes: found.size - expected.length,
    geometry_sha256: geometryHash,
  };
}
