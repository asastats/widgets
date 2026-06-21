/**
 * @file ASA Stats Folks Smart Router widget — browser controller (engine-backed).
 * @author ASA Stats
 *
 * Router-agnostic swap flow + the Folks adapter (wired against
 * @folks-router/js-sdk). Sibling router widgets reuse the RouterAdapter shape;
 * only the adapter implementation differs.
 *
 * DATA FLOW (engine-backed):
 *  - The shell renders one collapsible per linked address. Opening a section
 *    lazy-loads its swap panel via htmx from `account:holdings` (the widget's
 *    FolksHoldingsView -> engine_request). The panel embeds a JSON island
 *    (`.id-folks-holdings`) that is this controller's source of truth for the SDK.
 *  - The target search box is htmx-wired in the template to `assets:lookup`; this
 *    controller only handles selecting a returned `.id-folks-asset-option`.
 *  - Opt-in is detected client-side (target id present in the holdings island).
 *    On Swap the controller re-reads fresh holdings, and if the target is not
 *    opted in it runs `window.asastatsSwap.optIn` as a separate pre-flight txn
 *    before building and signing the Folks group.
 *
 * The ASA Stats fee is taken natively by Folks via `feeBps` + `referrer` on the
 * quote; no fee txn is appended here, so the returned group is signed as-is.
 */

/** @type {Object} The Folks RouterAdapter (getQuote / buildSwapGroup). */
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
      amount: p.amount,
      swapMode: SwapMode.FIXED_INPUT,
    };
    var sq = await client.fetchSwapQuote(
      params,
      undefined,
      cfg.feeBps || undefined,
      undefined,
      cfg.referrer || undefined
    );
    var slippageBps = Math.round((p.slippagePct || 0) * 100);
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
    return base64Txns.map(b64ToBytes);
  },
};

/** Router registry — one entry per swap widget. */
var ROUTERS = { folks: FolksAdapter };

var QUOTE_DEBOUNCE_MS = 400;

/** Read non-secret router config from the shell root element. */
function folksConfig(root) {
  return {
    network: root.dataset.network || "mainnet",
    referrer: root.dataset.referrer || "",
    feeBps: Number(root.dataset.feeBps || "0"),
  };
}

/** Parse a panel's holdings JSON island into an array of holdings. */
function readPanelHoldings(panel) {
  var el = panel.querySelector(".id-folks-holdings");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent || "[]");
  } catch (e) {
    return [];
  }
}

/** True when `assetId` is among the address' opted-in holdings. */
function isOptedIn(holdings, assetId) {
  var id = Number(assetId);
  return holdings.some(function (h) {
    return Number(h.id) === id;
  });
}

/** Fetch fresh holdings for a re-check without disturbing the visible form. */
async function fetchHoldings(url) {
  var resp = await fetch(url, { headers: { "HX-Request": "true" } });
  var html = await resp.text();
  var doc = new DOMParser().parseFromString(html, "text/html");
  var island = doc.querySelector(".id-folks-holdings");
  if (!island) return [];
  try {
    return JSON.parse(island.textContent || "[]");
  } catch (e) {
    return [];
  }
}

/** Set the chosen target on the panel and toggle the opt-in notice. */
function selectTarget(panel, optionEl, ctx) {
  var toHidden = panel.querySelector(".id-folks-to");
  toHidden.value = optionEl.dataset.id;
  toHidden.dataset.decimals = optionEl.dataset.decimals || "0";
  toHidden.dataset.unit = optionEl.dataset.unit || "";
  var opted = isOptedIn(readPanelHoldings(panel), optionEl.dataset.id);
  toHidden.dataset.optedIn = opted ? "1" : "0";
  panel.querySelector(".id-folks-optin-notice").style.display = opted
    ? "none"
    : "block";
  panel.querySelector(".id-folks-to-search").value =
    (optionEl.dataset.unit || "ASA") + " (#" + optionEl.dataset.id + ")";
  var results = panel.querySelector(".id-folks-to-results");
  if (results) results.innerHTML = "";
  scheduleQuote(panel, ctx);
}

/** Assemble QuoteParams from a panel; null until from/to/amount are complete. */
function readQuoteParams(panel, fromAddress) {
  var fromSel = panel.querySelector(".id-folks-from");
  var toHidden = panel.querySelector(".id-folks-to");
  var amountEl = panel.querySelector(".id-folks-amount");
  var slipEl = panel.querySelector(".id-folks-slippage");
  if (!fromSel || !fromSel.value || !toHidden.value || !amountEl.value) {
    return null;
  }
  var fromOpt = fromSel.options[fromSel.selectedIndex];
  var decimals = Number(fromOpt.dataset.decimals || "0");
  var amount = decimalToBaseUnits(amountEl.value, decimals);
  if (amount <= BigInt(0)) return null;
  return {
    fromAssetId: Number(fromSel.value),
    toAssetId: Number(toHidden.value),
    amount: amount,
    slippagePct: Number(slipEl.value || "0.5"),
    fromAddress: fromAddress,
  };
}

function scheduleQuote(panel, ctx) {
  clearTimeout(ctx.quoteTimer);
  ctx.quoteTimer = setTimeout(function () {
    refreshQuote(panel, ctx);
  }, QUOTE_DEBOUNCE_MS);
}

async function refreshQuote(panel, ctx) {
  var params = readQuoteParams(panel, ctx.fromAddress);
  var btn = panel.querySelector(".id-folks-swap-btn");
  if (!params) {
    if (btn) btn.disabled = true;
    return;
  }
  setPanelStatus(panel, "Fetching best route…");
  try {
    ctx.lastQuote = await ctx.adapter.getQuote(params, ctx.cfg);
    renderQuote(panel, ctx.lastQuote);
    setPanelStatus(panel, "");
    if (btn) btn.disabled = !ctx.owns;
  } catch (e) {
    setPanelStatus(panel, "Could not fetch a quote: " + (e && e.message));
    if (btn) btn.disabled = true;
  }
}

async function executeSwap(panel, ctx) {
  var params = readQuoteParams(panel, ctx.fromAddress);
  if (!params || !ctx.lastQuote) return;
  var btn = panel.querySelector(".id-folks-swap-btn");
  if (btn) btn.disabled = true;
  setPanelStatus(panel, "Re-checking balance…");
  try {
    var fresh = await fetchHoldings(ctx.holdingsUrl);
    var from = fresh.filter(function (h) {
      return Number(h.id) === params.fromAssetId;
    })[0];
    if (!from || BigInt(from.amount) < params.amount) {
      setPanelStatus(panel, "Insufficient balance — it may have changed.");
      return;
    }
    if (!isOptedIn(fresh, params.toAssetId)) {
      setPanelStatus(panel, "Opting into the target asset (one approval)…");
      await window.asastatsSwap.optIn(params.toAssetId);
    }
    setPanelStatus(panel, "Building transaction…");
    var group = await ctx.adapter.buildSwapGroup(
      ctx.lastQuote,
      ctx.fromAddress,
      ctx.cfg
    );
    setPanelStatus(panel, "Awaiting signature…");
    var txid = await window.asastatsSwap.signAndSend(group);
    setPanelStatus(panel, "Swap submitted: " + txid);
  } catch (e) {
    setPanelStatus(panel, "Swap failed or cancelled: " + (e && e.message));
  } finally {
    if (btn) btn.disabled = !ctx.owns;
  }
}

function renderQuote(panel, q) {
  var toHidden = panel.querySelector(".id-folks-to");
  var toDec = Number((toHidden && toHidden.dataset.decimals) || "0");
  var out = panel.querySelector(".id-folks-quote");
  if (!out) return;
  out.textContent =
    "≈ " +
    baseUnitsToDecimal(q.amountOut, toDec) +
    " (min " +
    baseUnitsToDecimal(q.minimumReceived, toDec) +
    ", impact " +
    q.priceImpactPct +
    "%, " +
    baseUnitsToDecimal(BigInt(q.feesTotal), 6) +
    " ALGO fee) via " +
    q.routeLabel;
}

function setPanelStatus(panel, msg) {
  var el = panel.querySelector(".id-folks-status");
  if (el) el.textContent = msg;
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

/* istanbul ignore next -- DOM/htmx wiring; the unit-tested core is the helpers above */
function impliedSource() {
  /* istanbul ignore next -- thin URL read; behaviour covered via applyImpliedSource */
  return new URLSearchParams(window.location.search).get("from");
}

function applyImpliedSource(panel, fromAsset) {
  if (!fromAsset) return false;
  var sel = panel.querySelector(".id-folks-from");
  if (!sel) return false;
  var match = sel.querySelector('option[value="' + fromAsset + '"]');
  if (!match) return false;
  sel.value = fromAsset;
  return true;
}

function bindPanel(panelEl, ctx) {
  ["id-folks-from", "id-folks-amount", "id-folks-slippage"].forEach(function (cls) {
    var el = panelEl.querySelector("." + cls);
    if (el) el.addEventListener("input", function () { scheduleQuote(panelEl, ctx); });
  });
  applyImpliedSource(panelEl, impliedSource());
  panelEl.addEventListener("click", function (ev) {
    var opt = ev.target.closest && ev.target.closest(".id-folks-asset-option");
    if (opt) selectTarget(panelEl, opt, ctx);
  });
  var btn = panelEl.querySelector(".id-folks-swap-btn");
  if (btn) {
    btn.disabled = !ctx.owns;
    btn.addEventListener("click", function () { executeSwap(panelEl, ctx); });
  }
}

/* istanbul ignore next -- htmx glue */
function loadPanel(panelEl, ctx) {
  var done = function () { bindPanel(panelEl, ctx); };
  if (window.htmx && window.htmx.ajax) {
    window.htmx
      .ajax("GET", ctx.holdingsUrl, { target: panelEl, swap: "innerHTML" })
      .then(done);
  } else {
    fetch(ctx.holdingsUrl)
      .then(function (r) { return r.text(); })
      .then(function (h) { panelEl.innerHTML = h; done(); });
  }
}

/* istanbul ignore next -- per-section wiring */
function wireSection(li, adapter, cfg, active) {
  var address = li.dataset.address;
  var header = li.querySelector(".collapsible-header");
  var panelEl = li.querySelector(".id-folks-panel");
  if (!header || !panelEl) return;
  var loaded = false;
  header.addEventListener("click", function () {
    if (loaded) return;
    loaded = true;
    loadPanel(panelEl, {
      adapter: adapter,
      cfg: cfg,
      fromAddress: address,
      owns: address === active,
      holdingsUrl: panelEl.dataset.holdingsUrl,
      quoteTimer: null,
    });
  });
}

/* istanbul ignore next -- entry-point wiring */
function mainFolks() {
  var root = document.getElementById("id-folks-swap");
  if (!root) return;
  var adapter = ROUTERS[root.dataset.router];
  if (!adapter) return;
  var cfg = folksConfig(root);
  var active =
    window.asastatsSwap && window.asastatsSwap.activeAddress
      ? window.asastatsSwap.activeAddress()
      : null;
  var items = root.querySelectorAll("#id-folks-addresses > li");
  Array.prototype.forEach.call(items, function (li) {
    wireSection(li, adapter, cfg, active);
  });
}

/* istanbul ignore next -- bridge-readiness gate */
function startFolks() {
  if (window.asastatsSwap) {
    mainFolks();
  } else {
    window.addEventListener("asastats:swap-ready", mainFolks, { once: true });
  }
}

/* istanbul ignore else -- in the browser we self-start; under jest we export */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    FolksAdapter: FolksAdapter,
    ROUTERS: ROUTERS,
    folksConfig: folksConfig,
    readPanelHoldings: readPanelHoldings,
    isOptedIn: isOptedIn,
    fetchHoldings: fetchHoldings,
    selectTarget: selectTarget,
    readQuoteParams: readQuoteParams,
    impliedSource: impliedSource,
    applyImpliedSource: applyImpliedSource,
    scheduleQuote: scheduleQuote,
    refreshQuote: refreshQuote,
    executeSwap: executeSwap,
    renderQuote: renderQuote,
    setPanelStatus: setPanelStatus,
    decimalToBaseUnits: decimalToBaseUnits,
    baseUnitsToDecimal: baseUnitsToDecimal,
    b64ToBytes: b64ToBytes,
    bindPanel: bindPanel,
    loadPanel: loadPanel,
    wireSection: wireSection,
    mainFolks: mainFolks,
    startFolks: startFolks,
  };
} else {
  /* istanbul ignore next -- browser entry point */
  startFolks();
}
