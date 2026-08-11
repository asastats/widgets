// Bundled into static/hogswap/hogswap-sdk.bundle.js as the `HogswapRouter`
// global. Build: see package.json `build:sdk`. Re-exports only what the shared
// swap controller needs from the HOGSWAP SDK.
//
// The error classes come too, because the controller has to tell a pair with
// no route (NoRouteError, a normal answer) from a quote that expired before
// the wallet was prompted (QuoteExpiredError, worth retrying) from being rate
// limited (RateLimitError). Without them every failure is an opaque Error and
// the user is told the same thing about all three.
export {
  HogswapClient,
  NoRouteError,
  QuoteExpiredError,
  RateLimitError,
} from "hogswap-js-sdk";
