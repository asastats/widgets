// Polyfill Node's Buffer for the browser. @folks-router/js-sdk (via algosdk)
// uses Buffer when it builds/encodes transactions, but esbuild does not provide
// it for browser bundles -> "Buffer is not defined" at prepareSwapTransactions
// time (quotes are pure HTTP/JSON, so they work without it).
//
// Injected via esbuild --inject, so it runs BEFORE the SDK code, guaranteeing
// globalThis.Buffer exists by the time any transaction is built.
import { Buffer } from "buffer";
globalThis.Buffer = globalThis.Buffer || Buffer;
