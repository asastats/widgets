/**
 * @file ASA Stats Folks Smart Router widget — browser controller.
 * @author ASA Stats
 *
 * Router-agnostic swap flow + the Folks adapter (wired against
 * @folks-router/js-sdk). Sibling router widgets reuse the RouterAdapter shape;
 * only the adapter implementation differs.
 *
 * TWO SEAMS:
 *
 *  1. Folks SDK (vendored bundle). The SDK is an npm ESM package; bundle it to
 *     static/folks/folks-sdk.bundle.js exposing the global `FolksRouter`
 *     (FolksRouterClient, Network, SwapMode). See this widget's package.json
 *     `build:sdk` script (esbuild --format=iife --global-name=FolksRouter).
 *     The client talks to api.folksrouter.io over HTTPS (declared in
 *     widget.toml `hosts`); the free endpoint is browser-direct, so no secret
 *     key is exposed. A /pro apiKey would have to be proxied via the backend.
 *
 *  2. Wallet swap bridge (frontend/wallet repo). Provides
 *     `window.asastatsSwap.{activeAddress(), signAndSend(group)}` and dispatches
 *     `asastats:swap-ready` once the wallet manager has resumed. See swapBridge.
 *
 * The ASA Stats fee is taken natively by Folks via `feeBps` + `referrer` on the
 * quote (the fee accrues to a referrer logicsig). No fee transaction is appended
 * here, so the returned group is signed as-is — preserving the atomic,
 * non-custodial guarantee.
 */

/**
 * @typedef {Object} Quote
 * @property {bigint} amountOut        expected output (base units)
 * @property {bigint} minimumReceived  display floor after slippage (base units)
 * @property {number} priceImpactPct
 * @property {string} routeLabel
 * @property {number} feesTotal        network txn fee (microALGO)
 * @property {Object} raw              { swapQuote, params, slippageBps } for buildSwapGroup
 */

/**
 * @typedef {Object} QuoteParams
 * @property {number} fromAssetId
 * @property {number} toAssetId
 * @property {bigint} amount        input amount (base units)
 * @property {number} slippagePct
 * @property {string} fromAddress
 */

/**
 * @typedef {Object} FolksConfig
 * @property {string} network    "mainnet" | "testnet"
 * @property {string} referrer   ASA Stats fee-collecting address ("" disables the fee)
 * @property {number} feeBps     ASA Stats fee in basis points
 */

/**
 * RouterAdapter — the interface every router widget implements.
 * @typedef {Object} RouterAdapter
 * @property {(p: QuoteParams, cfg: FolksConfig) => Promise<Quote>} getQuote
 * @property {(q: Quote, fromAddress: string, cfg: FolksConfig) => Promise<Uint8Array[]>} buildSwapGroup
 */

/** @type {RouterAdapter} */
var FolksAdapter = {
  _client: null,

  _clientFor: function (cfg) {
    if (!FolksAdapter._client) {
      var Network = window.FolksRouter.Network;
      var network = cfg.network === "testnet" ? Network.TESTNET : Network.MAINNET;
      FolksAdapter._client = new window.FolksRouter.FolksRouterClient(network);
    }
    return FolksAdapter._client;
  },

  getQuote: async function (p, cfg) {
    var SwapMode = window.FolksRouter.SwapMode;
    var client = FolksAdapter._clientFor(cfg);
    var params = {
      fromAssetId: p.fromAssetId,
      toAssetId: p.toAssetId,
      amount: p.amount, // bigint base units
      swapMode: SwapMode.FIXED_INPUT,
    };
    // feeBps + referrer => Folks bakes the ASA Stats fee into the quote/txns.
    var sq = await client.fetchSwapQuote(
      params,
      undefined,
      cfg.feeBps || undefined,
      undefined,
      cfg.referrer || undefined
    );
    var slippageBps = Math.round((p.slippagePct || 0) * 100);
    // Display floor; the real min-output is enforced inside the prepared txns.
    var minOut =
      sq.quoteAmount - (sq.quoteAmount * BigInt(slippageBps)) / BigInt(10000);
    return {
      amountOut: sq.quoteAmount,
      minimumReceived: minOut,
      priceImpactPct: sq.priceImpact,
      routeLabel: "Folks Router",
      feesTotal: sq.microalgoTxnsFee,
      raw: { swapQuote: sq, params: params, slippageBps: slippageBps },
    };
  },

  buildSwapGroup: async function (quote, fromAddress, cfg) {
    var client = FolksAdapter._clientFor(cfg);
    var base64Txns = await client.prepareSwapTransactions(
      quote.raw.params,
      fromAddress,
      quote.raw.slippageBps,
      quote.raw.swapQuote
    );
    // Already grouped and fee-bearing; decode base64 -> bytes for the bridge.
    return base64Txns.map(b64ToBytes);
  },
};

/** Router registry — one entry per swap widget. */
var ROUTERS = {
  folks: FolksAdapter,
};

/** Curated swap targets with known decimals (extend as needed). ALGO id is 0. */
var KNOWN_ASSETS = [
  { id: 0, unit: "ALGO", decimals: 6 },
  { id: 31566704, unit: "USDC", decimals: 6 },
];

var QUOTE_DEBOUNCE_MS = 400;
var quoteTimer = null;

/** Read host-injected, non-secret router config from the root element. */
function folksConfig(root) {
  return {
    network: root.dataset.network || "mainnet",
    referrer: root.dataset.referrer || "",
    feeBps: Number(root.dataset.feeBps || "0"),
  };
}

/** Entry point: gate on linked ∩ active address, then bind the flow. */
function mainFolks() {
  var root = document.getElementById("id-folks-swap");
  if (!root) return;

  var ctx = {
    routerId: root.dataset.router,
    linked: (root.dataset.linkedAddresses || "").split(" ").filter(Boolean),
    cfg: folksConfig(root),
  };
  var adapter = ROUTERS[ctx.routerId];

  var active =
    window.asastatsSwap && window.asastatsSwap.activeAddress
      ? window.asastatsSwap.activeAddress()
      : null;
  var owns = active && ctx.linked.indexOf(active) !== -1;

  if (!adapter || !owns) {
    document.getElementById("id-folks-locked").style.display = "block";
    return;
  }

  ctx.adapter = adapter;
  ctx.fromAddress = active;
  document.getElementById("id-folks-form").style.display = "block";

  // Holdings are injected server-side (portfolio:asas), keyed by address, because
  // the public /api/v2 API is JWT-only and unreachable from the browser session.
  var holdings = readHoldings()[active] || [];
  var opts = buildAssetOptions(holdings);
  populateSelect(document.getElementById("id-from-asset"), opts.from);
  populateSelect(document.getElementById("id-to-asset"), opts.to);
  bindFolksEvents(ctx);
}

function bindFolksEvents(ctx) {
  ["id-from-asset", "id-to-asset", "id-amount", "id-slippage"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", function () { scheduleQuote(ctx); });
  });
  document
    .getElementById("id-swap-btn")
    .addEventListener("click", function () { executeSwap(ctx); });
}

function scheduleQuote(ctx) {
  clearTimeout(quoteTimer);
  quoteTimer = setTimeout(function () { refreshQuote(ctx); }, QUOTE_DEBOUNCE_MS);
}

async function refreshQuote(ctx) {
  var params = readQuoteParams(ctx);
  if (!params) return;
  setStatus("Fetching best route…");
  try {
    ctx.lastQuote = await ctx.adapter.getQuote(params, ctx.cfg);
    renderQuote(ctx.lastQuote);
    setStatus("");
    document.getElementById("id-swap-btn").disabled = false;
  } catch (e) {
    setStatus("Could not fetch a quote: " + e.message);
    document.getElementById("id-swap-btn").disabled = true;
  }
}

async function executeSwap(ctx) {
  if (!ctx.lastQuote) return;
  setStatus("Building transaction…");
  try {
    var group = await ctx.adapter.buildSwapGroup(
      ctx.lastQuote,
      ctx.fromAddress,
      ctx.cfg
    );
    setStatus("Awaiting signature…");
    var txid = await window.asastatsSwap.signAndSend(group);
    setStatus("Swap submitted: " + txid);
    // TODO(host): POST the confirmed txid (router, from/to, amounts) to a
    // backend log endpoint for accounting.
  } catch (e) {
    setStatus("Swap failed or cancelled: " + e.message);
  }
}

/** Parse the host-injected per-address holdings map: { address: AsaHolding[] }. */
function readHoldings() {
  var el = document.getElementById("id-folks-holdings");
  if (!el) return {};
  try {
    return JSON.parse(el.textContent || "{}");
  } catch (e) {
    return {};
  }
}

/**
 * Compose the from/to asset option lists.
 *  - from: ALGO plus held assets with a positive balance.
 *  - to:   curated known targets unioned with held assets (so decimals are known).
 * @param {Array<{id:number,unit:string,decimals:number,amount:number}>} holdings
 */
function buildAssetOptions(holdings) {
  var held = holdings
    .filter(function (h) { return Number(h.amount) > 0; })
    .map(function (h) {
      return { id: Number(h.id), unit: h.unit, decimals: Number(h.decimals) };
    });
  var algo = { id: 0, unit: "ALGO", decimals: 6 };
  return { from: unionById([algo], held), to: unionById(KNOWN_ASSETS, held) };
}

/** Concatenate asset lists, de-duplicating by id (first occurrence wins). */
function unionById(primary, extra) {
  var seen = {};
  var out = [];
  primary.concat(extra).forEach(function (a) {
    if (seen[a.id]) return;
    seen[a.id] = true;
    out.push(a);
  });
  return out;
}

/** Render asset <option>s carrying data-decimals for base-unit conversion. */
function populateSelect(sel, assets) {
  sel.innerHTML = "";
  assets.forEach(function (a) {
    var o = document.createElement("option");
    o.value = String(a.id);
    o.textContent = a.unit || "ASA " + a.id;
    o.dataset.decimals = String(a.decimals);
    sel.appendChild(o);
  });
}

/** Assemble QuoteParams from the form; null until it is complete. */
function readQuoteParams(ctx) {
  var fromSel = document.getElementById("id-from-asset");
  var toSel = document.getElementById("id-to-asset");
  var amountEl = document.getElementById("id-amount");
  var slipEl = document.getElementById("id-slippage");
  if (!fromSel.value || !toSel.value || !amountEl.value) return null;

  var decimals = Number(
    fromSel.options[fromSel.selectedIndex].dataset.decimals || "0"
  );
  var amount = decimalToBaseUnits(amountEl.value, decimals);
  if (amount <= BigInt(0)) return null;

  return {
    fromAssetId: Number(fromSel.value),
    toAssetId: Number(toSel.value),
    amount: amount,
    slippagePct: Number(slipEl.value || "0.5"),
    fromAddress: ctx.fromAddress,
  };
}

function renderQuote(q) {
  var toSel = document.getElementById("id-to-asset");
  var toDec = Number(toSel.options[toSel.selectedIndex].dataset.decimals || "0");
  document.getElementById("id-quote").style.display = "block";
  document.getElementById("id-quote-out").textContent = baseUnitsToDecimal(q.amountOut, toDec);
  document.getElementById("id-quote-min").textContent = baseUnitsToDecimal(q.minimumReceived, toDec);
  document.getElementById("id-quote-impact").textContent = q.priceImpactPct + "%";
  document.getElementById("id-quote-route").textContent = q.routeLabel;
  document.getElementById("id-quote-fees").textContent =
    baseUnitsToDecimal(BigInt(q.feesTotal), 6) + " ALGO network fee";
}

function setStatus(msg) {
  document.getElementById("id-folks-status").textContent = msg;
}

/** Parse a decimal string into integer base units (bigint), truncating extra dp. */
function decimalToBaseUnits(value, decimals) {
  var parts = String(value).trim().split(".");
  var whole = parts[0] || "0";
  var frac = (parts[1] || "").slice(0, decimals);
  while (frac.length < decimals) frac += "0";
  return BigInt(whole) * BigInt(10) ** BigInt(decimals) + BigInt(frac || "0");
}

/** Format integer base units (bigint) back to a decimal string. */
function baseUnitsToDecimal(value, decimals) {
  var v = BigInt(value);
  var base = BigInt(10) ** BigInt(decimals);
  var whole = v / base;
  var frac = (v % base).toString().padStart(decimals, "0").replace(/0+$/, "");
  return frac ? whole.toString() + "." + frac : whole.toString();
}

/** Decode a base64 string to a Uint8Array (browser, no Buffer). */
function b64ToBytes(b64) {
  var bin = atob(b64);
  var out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * Run the render gate once the wallet bridge is ready. The bridge resumes
 * sessions asynchronously and dispatches `asastats:swap-ready`; if it is already
 * present (loaded first) run immediately, otherwise wait for the event once.
 */
function startFolks() {
  if (window.asastatsSwap) {
    mainFolks();
  } else {
    window.addEventListener("asastats:swap-ready", mainFolks, { once: true });
  }
}

document.addEventListener("DOMContentLoaded", startFolks);

/* istanbul ignore else -- export hook for unit tests; no effect in the browser */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    buildAssetOptions: buildAssetOptions,
    unionById: unionById,
    populateSelect: populateSelect,
    decimalToBaseUnits: decimalToBaseUnits,
    baseUnitsToDecimal: baseUnitsToDecimal,
    b64ToBytes: b64ToBytes,
  };
}
