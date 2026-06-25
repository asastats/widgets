// Polyfill Node's Buffer for the browser (algosdk uses it when building txns).
// Injected via esbuild --inject so it runs before the SDK code. Same fix as the
// folks SDK bundle.
import { Buffer } from "buffer";
globalThis.Buffer = globalThis.Buffer || Buffer;