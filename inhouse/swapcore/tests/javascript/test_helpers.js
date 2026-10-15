/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

const fs = require("fs");
const path = require("path");

global.loadSwapHtml = () => {
  const html = fs.readFileSync(path.resolve(__dirname, "./index.html"), "utf8");
  document.documentElement.innerHTML = html.toString();
};

global.mockFolksRouter = (overrides = {}) => {
  const quote = overrides.quote || {
    quoteAmount: 2000000n,
    priceImpact: 0.12,
    microalgoTxnsFee: 3000,
    txnPayload: "PAYLOAD",
  };
  const client = {
    fetchSwapQuote: jest.fn().mockResolvedValue(quote),
    prepareSwapTransactions: jest
      .fn()
      .mockResolvedValue(overrides.txns || ["QUJD", "REVG"]),
  };
  window.FolksRouter = {
    FolksRouterClient: jest.fn().mockImplementation(() => client),
    Network: { MAINNET: "mainnet", TESTNET: "testnet" },
    SwapMode: { FIXED_INPUT: "FIXED_INPUT", FIXED_OUTPUT: "FIXED_OUTPUT" },
  };
  return client;
};

global.mockSwapBridge = (overrides = {}) => {
  window.asastatsSwap = {
    activeAddress: jest.fn(() => (overrides.active === undefined ? "AAAA" : overrides.active)),
    signAndSend: overrides.signAndSend || jest.fn().mockResolvedValue("TXID9"),
  };
  return window.asastatsSwap;
};

/**
 * A stand-in for the host's `Fiat` (the website's static/js/fiat.js) with the
 * calls the widgets make. Not the host's file: this repository is tested alone.
 */
global.fiatStub = (code = "USD", rate = 1, symbol = code === "USD" ? "$" : "") => ({
  code: () => code,
  rate: () => rate,
  fromUsd: (usd) => usd * rate,
  symbol: () => symbol,
  isFiatSide: (stored) => !!stored && stored !== "ALGO",
});
