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
/**
 * Normalised quote shape shared by every router adapter, so the controller
 * (renderQuote, executeSwap) never needs to know which router produced it.
 * `raw` carries the router-specific payload that adapter.buildSwapGroup /
 * adapter.executeSwap need later.
 */
function makeQuote(q) {
  return {
    // "sell" = fixed-input (user fixes the source amount, output is computed);
    // "buy" = fixed-output (user fixes the target amount, input is computed).
    mode: q.mode || "sell",
    // amountOut: output amount (computed for sell, the fixed target for buy).
    amountOut: q.amountOut,
    // amountIn: input amount (the fixed source for sell, computed for buy).
    amountIn: q.amountIn,
    // minimumReceived: output floor after slippage (sell only).
    minimumReceived: q.minimumReceived,
    // maximumSent: input ceiling after slippage (buy only).
    maximumSent: q.maximumSent,
    priceImpactPct: q.priceImpactPct || 0,
    routeLabel: q.routeLabel,
    feesTotal: q.feesTotal || 0,
    raw: q.raw || {},
  };
}

/** Human route label from a {protocol: percent} map, e.g. "Tinyman, Pact". */
function routeLabelFrom(flattened) {
  var names = flattened ? Object.keys(flattened) : [];
  return names.length ? names.join(", ") : "";
}

/** Minimum-received (base units) for a fixed-input quote at `slippagePct`. */
function minReceived(amountOut, slippagePct) {
  var bps = BigInt(Math.round((slippagePct || 0) * 100));
  return amountOut - (amountOut * bps) / BigInt(10000);
}

/** Maximum-sent (base units) for a fixed-output quote at `slippagePct`. */
function maxSent(amountIn, slippagePct) {
  var bps = BigInt(Math.round((slippagePct || 0) * 100));
  return amountIn + (amountIn * bps) / BigInt(10000);
}

/**
 * True when a router returned an empty / no-route quote: the computed side (output
 * for sell, required input for buy) is missing or zero. Some routers signal "no
 * route for this pair/size" with an all-zero quote rather than an error, and we
 * must not render that as "≈ 0" or let the user submit it.
 */
function quoteIsEmpty(quote) {
  if (!quote) return true;
  var computed = quote.mode === "buy" ? quote.amountIn : quote.amountOut;
  return computed == null || computed <= BigInt(0);
}

var FolksAdapter = {
  _client: null,

  _clientFor: function (cfg) {
    var Network = window.FolksRouter.Network;
    var key = cfg.network === "testnet" ? "testnet" : "mainnet";
    FolksAdapter._clients = FolksAdapter._clients || {};
    if (!FolksAdapter._clients[key]) {
      var network = key === "testnet" ? Network.TESTNET : Network.MAINNET;
      FolksAdapter._clients[key] = new window.FolksRouter.FolksRouterClient(network);
    }
    return FolksAdapter._clients[key];
  },

  _discounts: null,

  /**
   * The user's on-chain FOLKS fee discount, cached per address. A lookup failure
   * must never block quoting -- the discount is applied on-chain at swap time
   * regardless of whether the quote reflected it -- so on error we proceed with
   * no discount in the quote.
   */
  _discountFor: async function (client, address) {
    if (!address) return undefined;
    FolksAdapter._discounts = FolksAdapter._discounts || {};
    if (!(address in FolksAdapter._discounts)) {
      try {
        FolksAdapter._discounts[address] = await client.fetchUserDiscount(address);
      } catch (e) {
        FolksAdapter._discounts[address] = undefined;
      }
    }
    return FolksAdapter._discounts[address];
  },

  getQuote: async function (p, cfg) {
    var SwapMode = window.FolksRouter.SwapMode;
    var client = FolksAdapter._clientFor(cfg);
    var buy = p.mode === "buy";
    var params = {
      fromAssetId: p.fromAssetId,
      toAssetId: p.toAssetId,
      amount: p.amount, // fixed input (sell) or fixed output (buy)
      swapMode: buy ? SwapMode.FIXED_OUTPUT : SwapMode.FIXED_INPUT,
    };
    // Make the quote discount-aware. We deliberately pass NO feeBps: omitting it
    // lets the router apply its protocol-minimum fee (0.1%) with the referral
    // credited to our referrer, and means there is no client-supplied fee that a
    // user could tamper to 0. The referrer is server-rendered (settings), not
    // hardcoded here.
    var discount = await FolksAdapter._discountFor(client, p.fromAddress);
    var sq = await client.fetchSwapQuote(
      params,
      undefined, // maxGroupSize
      undefined, // feeBps — never set; protocol minimum applies
      discount, // userFeeDiscount
      cfg.referrer || undefined
    );
    var slippageBps = Math.round((p.slippagePct || 0) * 100);
    var raw = { swapQuote: sq, params: params, slippageBps: slippageBps };
    if (buy) {
      // FIXED_OUTPUT: quoteAmount is the required INPUT; the user fixed the output.
      return makeQuote({
        mode: "buy",
        amountIn: sq.quoteAmount,
        amountOut: p.amount,
        maximumSent: maxSent(sq.quoteAmount, p.slippagePct),
        priceImpactPct: sq.priceImpact,
        routeLabel: "Folks Router",
        feesTotal: sq.microalgoTxnsFee,
        raw: raw,
      });
    }
    // FIXED_INPUT: quoteAmount is the OUTPUT; the user fixed the input.
    return makeQuote({
      mode: "sell",
      amountOut: sq.quoteAmount,
      amountIn: p.amount,
      minimumReceived: minReceived(sq.quoteAmount, p.slippagePct),
      priceImpactPct: sq.priceImpact,
      routeLabel: "Folks Router",
      feesTotal: sq.microalgoTxnsFee,
      raw: raw,
    });
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
/**
 * Haystack order router (@txnlab/haystack-router). Unlike Folks it uses a config
 * object (apiKey + referrer), a `newQuote`/`newSwap().execute()` composer flow,
 * and groups that can mix user-signed and pre-signed (logic-sig) transactions --
 * so it OWNS execution via `executeSwap` (the controller delegates to it) rather
 * than returning an all-user-signed group for `signAndSend`. Opt-in is handled
 * by the SDK (`autoOptIn` + address), so no separate pre-flight is needed.
 */
var HaystackAdapter = {
  _clients: null,

  _clientFor: function (cfg) {
    // No feeBps is set: omitting it applies Haystack's protocol-minimum fee with
    // the referral credited to our referrer, and leaves no client fee to tamper.
    var key = (cfg.apiKey || "") + "|" + (cfg.referrer || "");
    HaystackAdapter._clients = HaystackAdapter._clients || {};
    if (!HaystackAdapter._clients[key]) {
      HaystackAdapter._clients[key] = new window.HaystackRouter.RouterClient({
        apiKey: cfg.apiKey,
        referrerAddress: cfg.referrer || undefined,
        autoOptIn: true,
      });
    }
    return HaystackAdapter._clients[key];
  },

  getQuote: async function (p, cfg) {
    var client = HaystackAdapter._clientFor(cfg);
    var buy = p.mode === "buy";
    // `address` lets autoOptIn detect whether the output-asset opt-in must be
    // bundled into the routed group.
    var sq = await client.newQuote({
      address: p.fromAddress || undefined,
      fromASAID: p.fromAssetId,
      toASAID: p.toAssetId,
      amount: p.amount, // fixed input (sell) or fixed output (buy)
      type: buy ? "fixed-output" : "fixed-input",
    });
    // For fixed-output `sq.quote` is the required INPUT; for fixed-input it's the
    // OUTPUT received.
    var computed = BigInt(sq.quote);
    var impact =
      sq.userPriceImpact != null ? sq.userPriceImpact : sq.marketPriceImpact;
    var label = routeLabelFrom(sq.flattenedRoute) || "Haystack Router";
    var raw = { swapQuote: sq, slippagePct: p.slippagePct || 0 };
    if (buy) {
      return makeQuote({
        mode: "buy",
        amountIn: computed,
        amountOut: p.amount,
        maximumSent: maxSent(computed, p.slippagePct),
        priceImpactPct: impact,
        routeLabel: label,
        feesTotal: 0,
        raw: raw,
      });
    }
    return makeQuote({
      mode: "sell",
      amountOut: computed,
      amountIn: p.amount,
      minimumReceived: minReceived(computed, p.slippagePct),
      priceImpactPct: impact,
      routeLabel: label,
      feesTotal: 0,
      raw: raw,
    });
  },

  // Router-owned execution: the SDK composer signs (via the wallet bridge's
  // haystackSigner) and submits, returning the submitted txid.
  //
  // haystackSigner (not bridge.signer) is required here: Haystack calls the
  // signer with live Transaction objects from its own bundle, whereas
  // use-wallet's raw transactionSigner (bridge.signer) expects encoded
  // Uint8Array[]. Passing bridge.signer causes a DataView overread at sign
  // time because use-wallet re-encodes a "foreign" Transaction object using
  // its own algosdk class, reading past its internal byte buffer.
  // haystackSigner pre-encodes each Transaction to bytes on our side first,
  // making the handoff safe regardless of bundle boundaries.
  executeSwap: async function (a, bridge) {
    var client = HaystackAdapter._clientFor(a.cfg);
    var swap = await client.newSwap({
      quote: a.quote.raw.swapQuote,
      address: a.fromAddress,
      slippage: a.quote.raw.slippagePct,
      signer: bridge.haystackSigner,
    });
    var result = await swap.execute();
    return (result && result.txIds && result.txIds[0]) || "";
  },
};

var ROUTERS = { folks: FolksAdapter, haystack: HaystackAdapter };

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
  var form = panel.querySelector(".id-folks-form");
  var mode = form && form.classList.contains("folks-mode-buy") ? "buy" : "sell";
  var fromOpt = fromSel.options[fromSel.selectedIndex];
  // Sell fixes the SOURCE amount (From decimals); Buy fixes the TARGET amount
  // (To decimals). The amount field's units depend on the mode.
  var decimals =
    mode === "buy"
      ? Number(toHidden.dataset.decimals || "0")
      : Number(fromOpt.dataset.decimals || "0");
  var amount = decimalToBaseUnits(amountEl.value, decimals);
  if (amount <= BigInt(0)) return null;
  return {
    mode: mode,
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
  clearQuote(panel); // drop any stale quote line before the new result arrives
  if (!params) {
    if (btn) btn.disabled = true;
    return;
  }
  setPanelStatus(panel, "Fetching best route…");
  try {
    ctx.lastQuote = await ctx.adapter.getQuote(params, ctx.cfg);
    if (quoteIsEmpty(ctx.lastQuote)) {
      setPanelStatus(
        panel,
        "No route available for this swap. Try a different amount or asset.",
        true
      );
      if (btn) btn.disabled = true;
      return;
    }
    renderQuote(panel, ctx.lastQuote);
    var affordErr = affordabilityError(panel, ctx.lastQuote);
    if (affordErr) {
      setPanelStatus(panel, affordErr, true);
      if (btn) btn.disabled = true;
      return;
    }
    setPanelStatus(panel, "");
    applyOwnership(panel, walletOwns(ctx.fromAddress));
  } catch (e) {
    setPanelStatus(panel, "Could not fetch a quote: " + (e && e.message), true);
    if (btn) btn.disabled = true;
  }
}

async function executeSwap(panel, ctx) {
  var params = readQuoteParams(panel, ctx.fromAddress);
  if (!params || !ctx.lastQuote) return;
  // Authoritative gate: the connected wallet must control the from-address right
  // now (it may have connected, disconnected, or switched since the quote). The
  // on-chain sender check is the ultimate backstop; this is the clear message.
  if (!walletOwns(ctx.fromAddress)) {
    setPanelStatus(panel, "Connect the wallet for this address to swap.", true);
    return;
  }
  var btn = panel.querySelector(".id-folks-swap-btn");
  if (btn) btn.disabled = true;
  var submitted = false;
  setPanelStatus(panel, "Re-checking balance…");
  try {
    var fresh = await fetchHoldings(ctx.holdingsUrl);
    var from = fresh.filter(function (h) {
      return Number(h.id) === params.fromAssetId;
    })[0];
    var requiredInput =
      ctx.lastQuote.mode === "buy" ? ctx.lastQuote.maximumSent : params.amount;
    if (!from || BigInt(from.amount) < requiredInput) {
      setPanelStatus(panel, "Insufficient balance — it may have changed.", true);
      return;
    }
    var txid;
    if (typeof ctx.adapter.executeSwap === "function") {
      // Router owns build + opt-in + sign + submit (e.g. Haystack's composer).
      setPanelStatus(panel, "Awaiting signature…");
      txid = await ctx.adapter.executeSwap(
        {
          params: params,
          quote: ctx.lastQuote,
          fromAddress: ctx.fromAddress,
          cfg: ctx.cfg,
          holdings: fresh,
        },
        window.asastatsSwap
      );
    } else {
      // Legacy path (Folks): build the all-user-signed swap group. The bridge
      // prepends — into THIS atomic group (Folks' Option 2 / shape B) — the
      // user's target-asset opt-in if needed, and the per-referrer escrow's
      // logic-sig opt-in if a referrer is set and its escrow isn't opted in yet.
      setPanelStatus(panel, "Building transaction…");
      var group = await ctx.adapter.buildSwapGroup(
        ctx.lastQuote,
        ctx.fromAddress,
        ctx.cfg
      );
      var userNeedsOptIn = !isOptedIn(fresh, params.toAssetId);
      setPanelStatus(
        panel,
        userNeedsOptIn || (ctx.cfg && ctx.cfg.referrer)
          ? "Awaiting signature (may include opt-in)…"
          : "Awaiting signature…"
      );
      txid = await window.asastatsSwap.signAndSend(group, {
        outputAssetId: params.toAssetId,
        userNeedsOptIn: userNeedsOptIn,
        referrer: (ctx.cfg && ctx.cfg.referrer) || "",
      });
    }
    renderSwapSuccess(panel, txid);
    markSwapDirty(panel);
    submitted = true;
  } catch (e) {
    setPanelStatus(panel, "Swap failed or cancelled: " + (e && e.message), true);
  } finally {
    // Keep the button disabled after a successful submit (the amount was
    // cleared); on failure, restore it to the owner's normal state.
    if (btn) btn.disabled = submitted || !ctx.owns;
  }
}

function renderQuote(panel, q) {
  var out = panel.querySelector(".id-folks-quote");
  if (!out) return;
  var fromSel = panel.querySelector(".id-folks-from");
  var fromOpt = fromSel && fromSel.options[fromSel.selectedIndex];
  if (q.mode === "buy") {
    // Fixed-output: show the required INPUT (and the slippage-padded ceiling) in
    // the source asset's units.
    var fromDec = Number((fromOpt && fromOpt.dataset.decimals) || "0");
    var fromUnit = (fromOpt && fromOpt.dataset.unit) || "";
    out.textContent =
      "≈ " +
      baseUnitsToDecimal(q.amountIn, fromDec) +
      " " +
      fromUnit +
      " (max " +
      baseUnitsToDecimal(q.maximumSent, fromDec) +
      ", impact " +
      q.priceImpactPct +
      "%, " +
      baseUnitsToDecimal(BigInt(q.feesTotal), 6) +
      " ALGO fee) via " +
      q.routeLabel;
    return;
  }
  // Fixed-input: show the OUTPUT received (and the slippage floor) in target units.
  var toHidden = panel.querySelector(".id-folks-to");
  var toDec = Number((toHidden && toHidden.dataset.decimals) || "0");
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

/**
 * Returns an error string when the user can't cover the source side of the quote,
 * else "". Sell (fixed-input) checks the entered input amount; Buy (fixed-output)
 * checks the slippage-padded maximum input. Both compare against the holdings of
 * the source (From) asset.
 */
function affordabilityError(panel, quote) {
  if (!quote) return "";
  var buy = quote.mode === "buy";
  var required = buy ? quote.maximumSent : quote.amountIn;
  if (required == null) return "";
  var held = sourceHoldingsBaseUnits(panel);
  if (held === null) return "";
  if (required > held) {
    var sel = panel.querySelector(".id-folks-from");
    var opt = sel.options[sel.selectedIndex];
    var dec = Number(opt.dataset.decimals || "0");
    var unit = opt.dataset.unit || "";
    var need = baseUnitsToDecimal(required, dec) + " " + unit;
    var have = baseUnitsToDecimal(held, dec) + " " + unit;
    return buy
      ? "Need up to " + need + " but you have " + have + "."
      : "You only have " + have + " (tried to sell " + need + ").";
  }
  return "";
}

/**
 * Mirror the selected source (From) holdings into the "you own / pay with" helper
 * text so the user sees their maximum without opening the dropdown.
 */
function updateSourceMax(panel) {
  var sel = panel.querySelector(".id-folks-from");
  var maxEl = panel.querySelector(".id-folks-from-max");
  if (!sel || !maxEl) return;
  var opt = sel.options[sel.selectedIndex];
  if (!opt || opt.dataset.amount === undefined) {
    maxEl.textContent = "";
    return;
  }
  var dec = Number(opt.dataset.decimals || "0");
  var unit = opt.dataset.unit || "";
  maxEl.textContent =
    " — " + baseUnitsToDecimal(BigInt(opt.dataset.amount), dec) + " " + unit;
}

function clearQuote(panel) {
  var el = panel.querySelector(".id-folks-quote");
  if (el) el.textContent = "";
}

function setPanelStatus(panel, msg, isError) {
  var el = panel.querySelector(".id-folks-status");
  if (el) {
    el.textContent = msg;
    el.classList.toggle("id-folks-status-error", !!isError);
  }
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

/** Read the router cfg island the holdings partial embeds (`.id-folks-cfg`). */
function readPanelCfg(panelEl) {
  var el = panelEl.querySelector(".id-folks-cfg");
  if (!el) return null;
  return {
    router: el.dataset.router || "",
    network: el.dataset.network || "mainnet",
    referrer: el.dataset.referrer || "",
    feeBps: Number(el.dataset.feeBps || "0"),
  };
}

/** Build a holdings URL from the per-user marker template + connected address. */
function inlineHoldingsUrl(tmpl, address, fromAsset) {
  if (!tmpl || !address) return "";
  var url = tmpl.replace("ADDRESS", address);
  return fromAsset ? url + "?from=" + encodeURIComponent(fromAsset) : url;
}

/** Toggle an inline swap panel + its button label; returns true when now shown. */
function toggleInlineSwap(wrap, labelEl, labels) {
  var nowHidden = wrap.classList.toggle("hidden");
  if (labelEl) labelEl.textContent = nowHidden ? labels.show : labels.hide;
  return !nowHidden;
}

/**
 * Read the per-user marker's router config. The marker is non-cached, so it can
 * safely carry the viewer's chosen router + that router's public client config
 * (network / referrer / fee). Resolving the adapter + cfg here means a quote
 * never depends on an island inside the (separately fetched) holdings partial.
 */
function markerCfg(marker) {
  if (!marker) return null;
  return {
    router: marker.dataset.router || "",
    network: marker.dataset.network || "mainnet",
    referrer: marker.dataset.referrer || "",
    feeBps: Number(marker.dataset.feeBps || "0"),
    apiKey: marker.dataset.apiKey || "",
  };
}

/** Decimal-string amount that `pct`% of `base` holding base units represents. */
function applyPercent(base, decimals, pct) {
  var b = BigInt(base);
  var p = Math.max(0, Math.min(100, Number(pct) || 0));
  // Scale by 1e4 so a fractional percent (e.g. 33.33) keeps precision before
  // integer truncation back down to the asset's own decimals.
  var scaled = (b * BigInt(Math.round(p * 100))) / BigInt(10000);
  return baseUnitsToDecimal(scaled, decimals);
}

/** Holding base units (bigint) of the currently selected source asset, or null. */
function sourceHoldingsBaseUnits(panel) {
  var sel = panel.querySelector(".id-folks-from");
  if (!sel || !sel.value) return null;
  var opt = sel.options[sel.selectedIndex];
  if (!opt || opt.dataset.amount === undefined) return null;
  return BigInt(opt.dataset.amount || "0");
}

/** Set the amount field to `pct`% of the selected source holding; returns it. */
function setAmountFromPercent(panel, pct) {
  var sel = panel.querySelector(".id-folks-from");
  var amountEl = panel.querySelector(".id-folks-amount");
  var base = sourceHoldingsBaseUnits(panel);
  if (!sel || !amountEl || base === null) return "";
  var opt = sel.options[sel.selectedIndex];
  var decimals = Number((opt && opt.dataset.decimals) || "0");
  var value = applyPercent(base, decimals, pct);
  amountEl.value = value;
  return value;
}

/** Flip the source/target columns between "sell" (default) and "buy". */
function applySwapMode(formEl, mode) {
  if (!formEl) return "sell";
  var buy = mode === "buy";
  formEl.classList.toggle("folks-mode-buy", buy);
  return buy ? "buy" : "sell";
}

/**
 * Re-target the panel around the constant ANCHOR asset (the one whose Swap button
 * was clicked). On Sell the anchor is the From -- you sell it and pick the To. On
 * Buy the anchor is the To -- you buy it and pick the From (the asset you spend)
 * from your holdings. The anchor is captured from the From value on the first
 * switch and remembered on the panel for later switches.
 *
 * Returns { mode, ok, reason }; ok is false with reason "no-source" when a Buy has
 * no non-anchor holding available to spend.
 */
function retargetForMode(panel, mode) {
  var fromSel = panel.querySelector(".id-folks-from");
  var toHidden = panel.querySelector(".id-folks-to");
  var toSearch = panel.querySelector(".id-folks-to-search");
  var anchorId = panel.dataset.anchorId || fromSel.value || "";
  panel.dataset.anchorId = anchorId;
  if (mode === "buy") {
    var anchorOpt = fromSel.querySelector('option[value="' + anchorId + '"]');
    // Lock the target (To) to the anchor -- the asset being bought.
    toHidden.value = anchorId;
    toHidden.dataset.decimals = (anchorOpt && anchorOpt.dataset.decimals) || "0";
    toHidden.dataset.unit = (anchorOpt && anchorOpt.dataset.unit) || "";
    toHidden.dataset.optedIn = "1"; // the anchor is held, so already opted in
    panel.querySelector(".id-folks-optin-notice").style.display = "none";
    var anchorUnit = (anchorOpt && anchorOpt.dataset.unit) || "asset";
    // Leave the search box EMPTY so typing searches cleanly; advertise the default
    // buy target in the placeholder. The actual default selection lives in the
    // hidden input, so a quote works with no further interaction, and the user can
    // type to pick a different asset to buy.
    toSearch.value = "";
    toSearch.placeholder =
      "Buying " + anchorUnit + " (#" + anchorId + ") — type to change";
    panel.querySelector(".id-folks-to-results").innerHTML = "";
    // Default the source (From) to the first held asset that is NOT the anchor.
    var src = "";
    for (var i = 0; i < fromSel.options.length; i++) {
      if (fromSel.options[i].value !== anchorId) {
        src = fromSel.options[i].value;
        break;
      }
    }
    if (!src) return { mode: "buy", ok: false, reason: "no-source" };
    fromSel.value = src;
    return { mode: "buy", ok: true };
  }
  // Sell: the anchor is the From again; the To returns to a free search picker.
  fromSel.value = anchorId;
  toHidden.value = "";
  toHidden.dataset.decimals = "";
  toHidden.dataset.unit = "";
  toHidden.dataset.optedIn = "";
  toSearch.value = "";
  toSearch.placeholder = "To asset: name, unit, or ID";
  panel.querySelector(".id-folks-optin-notice").style.display = "none";
  return { mode: "sell", ok: true };
}

/** allo.info explorer URL for a transaction id. */
function alloTxUrl(txid) {
  return "https://allo.info/tx/" + encodeURIComponent(txid);
}

/**
 * Render a successful submission: a tappable allo.info link for the txid, then
 * reset the form to a clean state (clear amount + percentage + the now-stale
 * quote). The Swap button is left for executeSwap to disable, since the cleared
 * amount means there's nothing valid to re-submit.
 */
function renderSwapSuccess(panel, txid) {
  var status = panel.querySelector(".id-folks-status");
  if (status) {
    status.classList.remove("id-folks-status-error");
    status.textContent = "Swap submitted: ";
    var a = document.createElement("a");
    a.className = "id-folks-tx-link";
    a.href = alloTxUrl(txid);
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = txid;
    status.appendChild(a);
  }
  var amount = panel.querySelector(".id-folks-amount");
  if (amount) amount.value = "";
  var pct = panel.querySelector(".id-folks-pct");
  if (pct) pct.value = "";
  var quote = panel.querySelector(".id-folks-quote");
  if (quote) quote.textContent = "";
}

/**
 * Flag the enclosing modal "dirty" after a successful swap so closing it can
 * refresh now-stale holdings on the parent page. Returns whether a modal was
 * found (no-op on the shell accordion, which has no modal).
 */
function markSwapDirty(panel) {
  var modal = panel.closest && panel.closest(".modal");
  if (modal) modal.dataset.folksDirty = "1";
  return !!modal;
}

/**
 * Whether the live wallet bridge is connected to `address`. The bridge
 * (`window.asastatsSwap`) is published asynchronously after the per-user marker
 * loads and the wallet manager initialises, so this returns false until then and
 * whenever no wallet (or a different account) is connected. Holdings + quotes
 * need no connection; only signing does, so the swap UI stays gated on this.
 */
function walletOwns(address) {
  return !!(
    address &&
    window.asastatsSwap &&
    window.asastatsSwap.activeAddress &&
    window.asastatsSwap.activeAddress() === address
  );
}

/** Reflect ownership in the panel: enable/disable Swap + show the connect hint. */
function applyOwnership(panel, owns) {
  var btn = panel.querySelector(".id-folks-swap-btn");
  if (btn) btn.disabled = !owns;
  var notice = panel.querySelector(".id-folks-connect-notice");
  if (notice) notice.style.display = owns ? "none" : "block";
  return !!owns;
}

/* istanbul ignore next -- DOM event wiring; logic is covered via applyImpliedSource, applyPercent/setAmountFromPercent, and the scheduleQuote/selectTarget/executeSwap tests */
function bindPanel(panelEl, ctx) {
  ["id-folks-from", "id-folks-amount", "id-folks-slippage"].forEach(function (cls) {
    var el = panelEl.querySelector("." + cls);
    if (el)
      el.addEventListener("input", function () {
        updateSourceMax(panelEl);
        scheduleQuote(panelEl, ctx);
      });
  });
  if (!ctx.cfg) {
    var pc = readPanelCfg(panelEl);
    if (pc) {
      ctx.cfg = pc;
      ctx.adapter = ctx.adapter || ROUTERS[pc.router];
    }
  }
  applyImpliedSource(panelEl, ctx.from || impliedSource());
  // Re-anchor on every (re)load: the clicked asset becomes the fresh anchor, so
  // opening the modal from a different ASA's Swap button is captured correctly by
  // retargetForMode instead of reusing the previous session's anchor.
  delete panelEl.dataset.anchorId;
  updateSourceMax(panelEl);
  panelEl.addEventListener("click", function (ev) {
    var opt = ev.target.closest && ev.target.closest(".id-folks-asset-option");
    if (opt) { selectTarget(panelEl, opt, ctx); return; }
    var pb = ev.target.closest && ev.target.closest(".id-folks-pct-btn");
    if (pb) {
      setAmountFromPercent(panelEl, Number(pb.dataset.pct || "0"));
      scheduleQuote(panelEl, ctx);
    }
  });
  var pctInput = panelEl.querySelector(".id-folks-pct");
  if (pctInput) {
    pctInput.addEventListener("input", function () {
      setAmountFromPercent(panelEl, Number(pctInput.value || "0"));
      scheduleQuote(panelEl, ctx);
    });
  }
  applyOwnership(panelEl, ctx.owns);
  var btn = panelEl.querySelector(".id-folks-swap-btn");
  if (btn) {
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

/* istanbul ignore next -- delegated DOM glue; toggle/url logic is unit-tested */
function handleInlineSwapClick(ev) {
  var btn =
    ev.target.closest && ev.target.closest(".id-folks-swap-toggle");
  if (!btn) return;
  // Inline reveal owns the click; never navigate to the fallback href.
  ev.preventDefault();
  var wrap = document.getElementById(btn.dataset.folksTarget);
  if (!wrap) return;
  var panelEl = wrap.querySelector(".id-folks-panel");
  var labelEl = btn.querySelector(".swap-label");
  var shown = toggleInlineSwap(wrap, labelEl, {
    show: btn.dataset.labelShow || "Swap",
    hide: btn.dataset.labelHide || "Hide",
  });
  if (!shown || !panelEl || btn.dataset.folksLoaded) return;

  var marker = document.getElementById("id-swap-enabled");
  // Swap from the LINKED address the marker carries (the wallet-authenticated
  // account). Holdings + quote need no live wallet connection -- only the final
  // signature does -- so we never ask the user to reconnect just to look.
  var address = marker ? marker.dataset.address : "";
  if (!marker || !address) {
    panelEl.innerHTML =
      '<div class="id-folks-status id-folks-status-error">Swap is not available for this address.</div>';
    return;
  }
  btn.dataset.folksLoaded = "1";
  var from = btn.dataset.from || panelEl.dataset.from;
  loadPanel(panelEl, {
    fromAddress: address,
    owns: true,
    holdingsUrl: inlineHoldingsUrl(marker.dataset.holdingsTmpl, address, from),
    from: from,
    quoteTimer: null,
  });
}

/* istanbul ignore next -- DOM/modal glue; the quote + percent + mode logic is unit-tested */
function openSwapModal(fromAsset) {
  var modal = document.getElementById("folks-swap-modal");
  var marker = document.getElementById("id-swap-enabled");
  if (!modal) return;
  if (window.M && window.M.Modal) {
    (window.M.Modal.getInstance(modal) || window.M.Modal.init(modal)).open();
  }
  var cfg = markerCfg(marker);
  var address = marker ? marker.dataset.address || "" : "";
  var panelEl = modal.querySelector(".id-folks-panel");
  if (!panelEl) return;
  // Resolve the adapter + cfg from the marker, NOT from the loaded partial: a
  // quote must never fail just because the holdings island lacks router config.
  if (!cfg || !cfg.router || !ROUTERS[cfg.router] || !address) {
    panelEl.innerHTML =
      '<div class="id-folks-status id-folks-status-error">Swap is not available for this address.</div>';
    return;
  }
  if (panelEl.dataset.folksFrom === String(fromAsset) && panelEl.dataset.folksLoaded) {
    return;
  }
  panelEl.dataset.folksFrom = String(fromAsset || "");
  panelEl.dataset.folksLoaded = "1";
  loadPanel(panelEl, {
    adapter: ROUTERS[cfg.router],
    cfg: cfg,
    fromAddress: address,
    owns: walletOwns(address),
    holdingsUrl: inlineHoldingsUrl(marker.dataset.holdingsTmpl, address, fromAsset),
    from: fromAsset,
    quoteTimer: null,
  });
}

/* istanbul ignore next -- delegated DOM glue; opens the modal for the clicked row */
function handleSwapModalClick(ev) {
  var btn = ev.target.closest && ev.target.closest(".id-folks-swap-toggle");
  if (!btn) return;
  ev.preventDefault(); // the href is a no-JS fallback only
  openSwapModal(btn.dataset.from || "");
}

/* istanbul ignore next -- tab glue; the layout flip itself is unit-tested via applySwapMode */
function wireSwapTabs() {
  var modal = document.getElementById("folks-swap-modal");
  if (!modal) return;
  modal.addEventListener("click", function (ev) {
    var tab = ev.target.closest && ev.target.closest("[data-folks-mode]");
    if (!tab) return;
    applySwapMode(modal.querySelector(".id-folks-form"), tab.dataset.folksMode);
    // The amount's meaning flips with the mode (source vs target), so clear the
    // amount + percentage + stale quote and re-gate the button until a fresh,
    // mode-correct quote arrives.
    var panel = modal.querySelector(".id-folks-panel");
    if (!panel) return;
    // Re-target the anchor: From on Sell, To on Buy (and pick a source to spend).
    var res = retargetForMode(panel, tab.dataset.folksMode);
    updateSourceMax(panel);
    var amt = panel.querySelector(".id-folks-amount");
    var pct = panel.querySelector(".id-folks-pct");
    var quote = panel.querySelector(".id-folks-quote");
    var status = panel.querySelector(".id-folks-status");
    var btn = panel.querySelector(".id-folks-swap-btn");
    if (amt) amt.value = "";
    if (pct) pct.value = "";
    if (quote) quote.textContent = "";
    if (status) {
      status.textContent = res.ok
        ? ""
        : "You hold no other assets to spend on a buy.";
    }
    if (btn) btn.disabled = true;
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
  // Swap buttons open a modal. One delegated listener, attached as soon as this
  // script runs; the marker (router + cfg + linked address) is read at click
  // time, so this needs neither the bridge nor htmx swap timing to be ready.
  document.addEventListener("click", handleSwapModalClick);
  var modal = document.getElementById("folks-swap-modal");
  if (modal && window.M) {
    var modalInst = window.M.Modal ? window.M.Modal.init(modal) : null;
    if (modalInst) {
      // After a successful swap the viewed holdings are stale; refresh the
      // parent page when the user closes the modal -- but only if a swap
      // actually marked it dirty, so a look-and-cancel never reloads.
      modalInst.options.onCloseEnd = function () {
        if (modal.dataset.folksDirty === "1") window.location.reload();
      };
    }
    var tabsEl = modal.querySelector(".tabs");
    if (tabsEl && window.M.Tabs) {
      var tabs = window.M.Tabs.getInstance(tabsEl) || window.M.Tabs.init(tabsEl);
      // Tabs initialised while the modal is display:none compute a zero-width
      // indicator and don't mark the active tab. Recompute once it's visible.
      if (modalInst) {
        modalInst.options.onOpenEnd = function () {
          tabs.updateTabIndicator();
        };
      }
    }
  }
  wireSwapTabs();
  // Shell page (accordion of addresses) still binds per-section after bridge.
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
    HaystackAdapter: HaystackAdapter,
    ROUTERS: ROUTERS,
    makeQuote: makeQuote,
    routeLabelFrom: routeLabelFrom,
    minReceived: minReceived,
    maxSent: maxSent,
    quoteIsEmpty: quoteIsEmpty,
    affordabilityError: affordabilityError,
    retargetForMode: retargetForMode,
    updateSourceMax: updateSourceMax,
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
    clearQuote: clearQuote,
    walletOwns: walletOwns,
    applyOwnership: applyOwnership,
    alloTxUrl: alloTxUrl,
    renderSwapSuccess: renderSwapSuccess,
    markSwapDirty: markSwapDirty,
    decimalToBaseUnits: decimalToBaseUnits,
    baseUnitsToDecimal: baseUnitsToDecimal,
    b64ToBytes: b64ToBytes,
    readPanelCfg: readPanelCfg,
    markerCfg: markerCfg,
    applyPercent: applyPercent,
    sourceHoldingsBaseUnits: sourceHoldingsBaseUnits,
    setAmountFromPercent: setAmountFromPercent,
    applySwapMode: applySwapMode,
    inlineHoldingsUrl: inlineHoldingsUrl,
    toggleInlineSwap: toggleInlineSwap,
    bindPanel: bindPanel,
    loadPanel: loadPanel,
    handleInlineSwapClick: handleInlineSwapClick,
    openSwapModal: openSwapModal,
    handleSwapModalClick: handleSwapModalClick,
    wireSwapTabs: wireSwapTabs,
    wireSection: wireSection,
    mainFolks: mainFolks,
    startFolks: startFolks,
  };
} else {
  /* istanbul ignore next -- browser entry point */
  startFolks();
}
