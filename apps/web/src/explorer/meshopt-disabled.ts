/** The approved local models are uncompressed. Avoid the vendor decoder's eager
 * WASM initialization under our strict CSP; compressed assets fail explicitly. */
function unsupported(): never {
  throw new Error('Meshopt-compressed models are not supported by this view');
}
export const MeshoptDecoder = {
  supported: false,
  ready: Promise.resolve(),
  decodeVertexBuffer: unsupported,
  decodeIndexBuffer: unsupported,
  decodeIndexSequence: unsupported,
  decodeGltfBuffer: unsupported,
};
