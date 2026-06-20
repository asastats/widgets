/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

const fs = require("fs");
const path = require("path");

global.loadFolksHtml = () => {
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
