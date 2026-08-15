/**
 * @file ASA Stats Smart Router widget — browser controller (engine-backed).
 * @author ASA Stats
 *
 * Router-agnostic swap flow + the Folks or Haystack adapter (wired against
 * @folks-router/js-sdk or @txnlab/haystack-router). Sibling router widgets
 * reuse the RouterAdapter shape; only the adapter implementation differs.
 *
 * DATA FLOW (engine-backed):
 *  - The shell renders one collapsible per linked address. Opening a section
 *    lazy-loads its swap panel via htmx from `account:holdings` (the widget's
 *    FolksHoldingsView -> engine_request). The panel embeds a JSON island
 *    (`.id-swap-holdings`) that is this controller's source of truth for the SDK.
 *  - The target search box is htmx-wired in the template to `assets:lookup`; this
 *    controller only handles selecting a returned `.id-swap-asset-option`.
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
    // null -- NOT 0 -- when the router does not report one. Some routers never
    // compute price impact, and rendering their silence as a confident "0%" is
    // a claim we would be making on their behalf.
    priceImpactPct: q.priceImpactPct == null ? null : q.priceImpactPct,
    routeLabel: q.routeLabel,
    // [{name, pct}] per venue, when the router breaks the route down. `pct` is
    // null for routers that name their venues without weighting them.
    routeParts: q.routeParts || [],
    feesTotal: q.feesTotal || 0,
    raw: q.raw || {},
  };
}

/** Human route label from a {protocol: percent} map, e.g. "Tinyman, Pact". */
function routeLabelFrom(flattened) {
  var names = flattened ? Object.keys(flattened) : [];
  return names.length ? names.join(", ") : "";
}

/**
 * The same map as [{name, pct}], keeping the split the label throws away. A
 * route that is 62% Tinyman and 38% Pact is a materially different trade from
 * one that is 99/1, and the router already told us which it is.
 */
function routePartsFrom(flattened) {
  if (!flattened) return [];
  return Object.keys(flattened).map(function (name) {
    var pct = Number(flattened[name]);
    return { name: name, pct: isNaN(pct) ? null : pct };
  });
}

/** [{name, pct:null}] from an ordered list of venue names (one per hop). */
function routePartsFromNames(names) {
  return (names || []).map(function (name) {
    return { name: name, pct: null };
  });
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
    var parts = routePartsFrom(sq.flattenedRoute);
    var raw = { swapQuote: sq, slippagePct: p.slippagePct || 0 };
    if (buy) {
      return makeQuote({
        mode: "buy",
        amountIn: computed,
        amountOut: p.amount,
        maximumSent: maxSent(computed, p.slippagePct),
        priceImpactPct: impact,
        routeLabel: label,
        routeParts: parts,
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
      routeParts: parts,
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

/**
 * ASA Stats' own smart router. Unlike the other two there is no vendor SDK in
 * the browser: the routing is ours and it runs in the engine, so the adapter
 * posts to this widget's own endpoints and the widget proxies them under its
 * declared scopes.
 *
 * Two consequences worth knowing when reading this. Amounts cross as decimal
 * *strings* rather than numbers, because the controller works in BigInt base
 * units and JSON has no integer wide enough to be trusted with them. And there
 * is no client-side fee, referrer or slippage arithmetic to tamper with - the
 * quote arrives already carrying its own floor, computed against pool reserves
 * the browser never saw.
 */
var AsastatsAdapter = {
  /** Django's CSRF cookie, required because these are same-origin POSTs. */
  _csrfToken: function () {
    var match = /(?:^|;\s*)csrftoken=([^;]*)/.exec(document.cookie || "");
    return match ? decodeURIComponent(match[1]) : "";
  },

  _post: async function (url, address, body) {
    if (!url) throw new Error("this deployment has no ASA Stats router endpoint");
    // the address rides in the query string because the view gates on it
    // before the body is read at all
    var response = await fetch(url + "?address=" + encodeURIComponent(address), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": AsastatsAdapter._csrfToken(),
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error("ASA Stats router request failed (" + response.status + ")");
    }
    return await response.json();
  },

  getQuote: async function (p, cfg) {
    var buy = p.mode === "buy";
    var quoted = await AsastatsAdapter._post(cfg.quoteUrl, p.fromAddress, {
      from_asset_id: p.fromAssetId,
      to_asset_id: p.toAssetId,
      amount: String(p.amount), // fixed input (sell) or fixed output (buy)
      mode: buy ? "buy" : "sell",
      slippage_pct: p.slippagePct || 0,
    });
    // `raw` carries the engine's own quote back to buildSwapGroup, so the
    // group is built from the allocation that was actually quoted rather than
    // from one re-derived against reserves that have since moved.
    var raw = { quote: quoted };
    if (buy) {
      return makeQuote({
        mode: "buy",
        amountIn: BigInt(quoted.amount_in),
        amountOut: BigInt(quoted.minimum_received),
        // exact rather than a tolerance: our legs are fixed-input, so nothing
        // can make the group spend more than it was built to spend
        maximumSent: BigInt(quoted.maximum_sent),
        priceImpactPct: quoted.price_impact_pct,
        routeLabel: quoted.route_label,
        feesTotal: quoted.fees_total,
        raw: raw,
      });
    }
    return makeQuote({
      mode: "sell",
      amountOut: BigInt(quoted.amount_out),
      amountIn: BigInt(quoted.amount_in),
      minimumReceived: BigInt(quoted.minimum_received),
      priceImpactPct: quoted.price_impact_pct,
      routeLabel: quoted.route_label,
      feesTotal: quoted.fees_total,
      raw: raw,
    });
  },

   // The engine may return a partially signed group: the backend signs the
   // quote authorization and the wallet signs the user's transactions. Direct
   // groups remain arrays for the legacy bridge; routed groups return metadata
   // for signAndSendPartial. The engine refuses Tinyman v1 legs because those
   // require a provider logic signature as well.
  buildSwapGroup: async function (quote, fromAddress, cfg) {
    var built = await AsastatsAdapter._post(cfg.groupUrl, fromAddress, {
      quote: quote.raw.quote,
    });
    var transactions = (built.transactions || []).map(b64ToBytes);
    if (built.signed_transactions && built.quote_signer_index !== undefined) {
      var signedTransactions = {};
      Object.keys(built.signed_transactions).forEach(function (index) {
        signedTransactions[index] = b64ToBytes(built.signed_transactions[index]);
      });
      return {
        transactions: transactions,
        signedTransactions: signedTransactions,
        quoteSignerIndex: Number(built.quote_signer_index),
      };
    }
    return transactions;
  },
};

/**
 * HOGSWAP (hogswap-js-sdk). Quotes over its own REST API and returns an
 * *unsigned* group from `/execute`, so unlike Haystack it does not own
 * execution: the controller's signAndSend path applies, as it does for our own
 * router.
 *
 * Three things about this router that the other adapters do not have to deal
 * with, all of them documented rather than discovered:
 *
 * - **A quote expires in 30 seconds** and `/execute` refuses a stale one. The
 *   controller quotes as the user types and builds only when they click, which
 *   is easily longer than that, so `buildSwapGroup` re-quotes once when the
 *   quote has expired rather than failing the swap.
 * - **Slippage is in basis points and must be 1-5000.** Zero is rejected
 *   outright, and the controller is free to offer it, so it is clamped.
 * - **Amounts arrive as JSON numbers**, not strings. Everything here works in
 *   BigInt base units, so they are converted once on the way in.
 *
 * There is no referrer or integrator fee parameter in this SDK: what the user
 * pays is HOGSWAP's own 5 bps, waived in proportion to the HOG their wallet
 * holds. Nothing accrues to us, which is why the widget manifest's
 * `revenue_account` is empty in fact and not merely by convention.
 */
var HogswapAdapter = {
  _clients: null,

  _clientFor: function (cfg) {
    var key = (cfg.baseUrl || "") + "|" + (cfg.apiKey || "");
    HogswapAdapter._clients = HogswapAdapter._clients || {};
    if (!HogswapAdapter._clients[key]) {
      HogswapAdapter._clients[key] = new window.HogswapRouter.HogswapClient({
        // both optional: an empty base URL means the SDK's own default, and
        // the free tier needs no key
        baseUrl: cfg.baseUrl || undefined,
        apiKey: cfg.apiKey || undefined,
      });
    }
    return HogswapAdapter._clients[key];
  },

  /** Whole base units as BigInt, from the JSON numbers this API returns. */
  _units: function (value) {
    return BigInt(Math.round(Number(value || 0)));
  },

  /** Slippage in the 1-5000 basis points the API accepts. */
  _bps: function (slippagePct) {
    var bps = Math.round((slippagePct || 0) * 100);
    return Math.max(1, Math.min(5000, bps));
  },

  /** Ask for a quote in whichever direction the caller fixed. */
  _quote: function (client, p) {
    var common = {
      assetIn: p.fromAssetId,
      assetOut: p.toAssetId,
      slippageBps: HogswapAdapter._bps(p.slippagePct),
      // prices this wallet's HOG fee discount rather than the list rate
      sender: p.fromAddress || undefined,
    };
    if (p.mode === "buy") {
      return client.exactOutQuote(
        Object.assign({ amountOut: Number(p.amount) }, common)
      );
    }
    return client.swapQuote(Object.assign({ amountIn: Number(p.amount) }, common));
  },

  getQuote: async function (p, cfg) {
    var client = HogswapAdapter._clientFor(cfg);
    var q = await HogswapAdapter._quote(client, p);
    // `raw` keeps the quote id and the parameters, so buildSwapGroup can both
    // execute this quote and re-issue it if it has expired by then
    var raw = { quoteId: q.quote_id, params: p, quote: q };
    var label = "HOGSWAP";
    var names = [];
    if (q.legs && q.legs.length) {
      // one entry per pool crossed; name the venues rather than count them
      for (var i = 0; i < q.legs.length; i++) {
        var name = q.legs[i].dex_name;
        if (name && names.indexOf(name) === -1) names.push(name);
      }
      if (names.length) label = names.join(", ");
    }
    var parts = routePartsFromNames(names);
    // This API returns no price impact at all, so the quote carries null and the
    // panel omits the row. It previously carried 0, which told every HOGSWAP
    // user their trade moved the price by exactly nothing.
    if (p.mode === "buy") {
      return makeQuote({
        mode: "buy",
        amountIn: HogswapAdapter._units(q.amount_in),
        amountOut: p.amount,
        // exact rather than a tolerance: exact-out already sizes the input so
        // its own on-chain floor covers the target, so nothing can make the
        // group spend more than this
        maximumSent: HogswapAdapter._units(q.amount_in),
        priceImpactPct: null,
        routeLabel: label,
        routeParts: parts,
        feesTotal: Number(q.network_fee_microalgo || 0),
        raw: raw,
      });
    }
    return makeQuote({
      mode: "sell",
      amountOut: HogswapAdapter._units(q.expected_out),
      amountIn: p.amount,
      // the router's own floor, which its contract enforces, rather than one
      // recomputed here - showing a number the chain will not act on would be
      // worse than showing theirs
      minimumReceived: HogswapAdapter._units(q.min_out_at_slippage),
      priceImpactPct: null,
      routeLabel: label,
      routeParts: parts,
      feesTotal: Number(q.network_fee_microalgo || 0),
      raw: raw,
    });
  },

  /**
   * All-user-signed, so the controller signs and submits. `/execute` returns
   * base64 msgpack transactions in group order.
   *
   * The re-quote on expiry is deliberate and worth understanding: a quote lives
   * 30 seconds and a user reading a confirmation dialog can easily outlast it.
   * Refusing would be safe and useless. Re-quoting risks a price that moved
   * since the screen was drawn - but the replacement carries its own
   * `min_out_at_slippage`, enforced by their contract, so the user cannot be
   * filled below the tolerance they chose. Better a fresh honest price than a
   * dead quote.
   */
  buildSwapGroup: async function (quote, fromAddress, cfg) {
    var client = HogswapAdapter._clientFor(cfg);
    var quoteId = quote.raw.quoteId;
    var built;
    try {
      built = await client.execute({ quoteId: quoteId, userAddress: fromAddress });
    } catch (e) {
      if (!(e instanceof window.HogswapRouter.QuoteExpiredError)) throw e;
      var fresh = await HogswapAdapter._quote(client, quote.raw.params);
      built = await client.execute({
        quoteId: fresh.quote_id,
        userAddress: fromAddress,
      });
    }
    return (built.txnsB64 || []).map(b64ToBytes);
  },
};

/** Router registry — one entry per swap widget. */
var ROUTERS = {
  folks: FolksAdapter,
  haystack: HaystackAdapter,
  asastats: AsastatsAdapter,
  hogswap: HogswapAdapter,
};

var QUOTE_DEBOUNCE_MS = 400;

//: How long a quote is treated as current. HOGSWAP expires its own at 30s and
//: refuses a stale one at /execute; the others do not expire, but re-pricing a
//: minute-old number costs one request and stops the panel showing a price the
//: chain would no longer give.
var QUOTE_TTL_MS = 30000;

//: Automatic re-prices before the panel gives up and waits for the user. Ten
//: covers five minutes of reading; an abandoned modal then stops on its own.
var QUOTE_AUTO_REFRESH_LIMIT = 10;

//: ALGO's asset id. Only ALGO pays a group's fees and a minimum balance, so it
//: is the one holding a percentage chip cannot offer in full.
var ALGO_ASSET_ID = 0;

//: microALGO held back for the group's own fees when picking a percentage of an
//: ALGO holding. A router group is several transactions and a multi-hop route
//: pools the fees of its inner ones too, so 0.03 covers roughly thirty of them
//: -- comfortably more than any route we send. The quote reports the real
//: figure as `feesTotal`, but the chips run before a quote exists.
var SWAP_FEE_HEADROOM = 30000;

//: What opting in to one more asset adds to an account's minimum balance. The
//: opt-in notice in the panel quotes the same 0.1 ALGO to the user.
var ASSET_OPTIN_MIN_BALANCE = 100000;

/** Read non-secret router config from the shell root element. */
function swapConfig(root) {
  return {
    network: root.dataset.network || "mainnet",
    referrer: root.dataset.referrer || "",
    feeBps: Number(root.dataset.feeBps || "0"),
    // Haystack's and HOGSWAP's rate-limit keys. Read here as well as in
    // `markerCfg` because a router's own shell page configures itself from this
    // element: without it Haystack's shell built an unkeyed client while the
    // inline modal built a keyed one, from the same template value.
    apiKey: root.dataset.apiKey || "",
    // HOGSWAP only, and optional there: empty means the SDK's own default host,
    // which is what production uses. It exists so a staging deployment can be
    // pointed elsewhere without a code change.
    baseUrl: root.dataset.baseUrl || "",
    // Only the ASA Stats router uses these: its quoting runs in our engine, so
    // the browser posts to us instead of to a vendor SDK. Empty for the others.
    quoteUrl: root.dataset.quoteUrl || "",
    groupUrl: root.dataset.groupUrl || "",
  };
}

/** Parse a panel's holdings JSON island into an array of holdings. */
function readPanelHoldings(panel) {
  var el = panel.querySelector(".id-swap-holdings");
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
  var island = doc.querySelector(".id-swap-holdings");
  if (!island) return [];
  try {
    return JSON.parse(island.textContent || "[]");
  } catch (e) {
    return [];
  }
}

/** Set the chosen target on the panel and toggle the opt-in notice. */
function selectTarget(panel, optionEl, ctx) {
  var toHidden = panel.querySelector(".id-swap-to");
  toHidden.value = optionEl.dataset.id;
  toHidden.dataset.decimals = optionEl.dataset.decimals || "0";
  toHidden.dataset.unit = optionEl.dataset.unit || "";
  toHidden.dataset.icon = optionEl.dataset.icon || "";
  var opted = isOptedIn(readPanelHoldings(panel), optionEl.dataset.id);
  toHidden.dataset.optedIn = opted ? "1" : "0";
  panel.querySelector(".id-swap-optin-notice").style.display = opted
    ? "none"
    : "block";
  panel.querySelector(".id-swap-to-search").value =
    (optionEl.dataset.unit || "ASA") + " (#" + optionEl.dataset.id + ")";
  var results = panel.querySelector(".id-swap-to-results");
  if (results) results.innerHTML = "";
  // The pill now carries the choice, so the sheet has done its job.
  syncAssetButtons(panel);
  closeAssetPicker(panel);
  scheduleQuote(panel, ctx);
}

/** Assemble QuoteParams from a panel; null until from/to/amount are complete. */
function readQuoteParams(panel, fromAddress) {
  var fromSel = panel.querySelector(".id-swap-from");
  var toHidden = panel.querySelector(".id-swap-to");
  var amountEl = panel.querySelector(".id-swap-amount");
  var slipEl = panel.querySelector(".id-swap-slippage");
  if (!fromSel || !fromSel.value || !toHidden.value || !amountEl.value) {
    return null;
  }
  var form = panel.querySelector(".id-swap-form");
  var mode = form && form.classList.contains("swap-mode-buy") ? "buy" : "sell";
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
  // A fresh edit restarts the automatic re-pricing budget: the cap exists to
  // stop an abandoned modal quoting forever, not to limit an active user.
  ctx.requotes = 0;
  ctx.quoteTimer = setTimeout(function () {
    refreshQuote(panel, ctx);
  }, QUOTE_DEBOUNCE_MS);
}

/**
 * Re-price the standing quote when it goes stale.
 *
 * A HOGSWAP quote lives 30 seconds and `buildSwapGroup` already re-quotes behind
 * the user's back when they click after that. Doing it in the open means the
 * price on screen is the price they get, and the ring in the summary says when
 * it will change. Capped, because a modal left open overnight must not keep
 * asking; paused while the tab is hidden and while a swap is being signed.
 */
function scheduleRequote(panel, ctx) {
  clearTimeout(ctx.requoteTimer);
  ctx.requotes = ctx.requotes || 0;
  if (ctx.requotes >= QUOTE_AUTO_REFRESH_LIMIT) return;
  ctx.requoteTimer = setTimeout(function () {
    if (ctx.swapping) return;
    if (typeof document !== "undefined" && document.hidden) {
      scheduleRequote(panel, ctx); // look again in another TTL
      return;
    }
    if (panel.isConnected === false) return;
    ctx.requotes += 1;
    refreshQuote(panel, ctx);
  }, QUOTE_TTL_MS);
}

async function refreshQuote(panel, ctx) {
  var params = readQuoteParams(panel, ctx.fromAddress);
  var btn = panel.querySelector(".id-swap-swap-btn");
  clearTimeout(ctx.requoteTimer);
  clearQuote(panel); // drop any stale quote line before the new result arrives
  if (!params) {
    if (btn) btn.disabled = true;
    setCtaLabel(panel, ctaLabelFor(panel));
    return;
  }
  setPanelStatus(panel, "Fetching best route…");
  setCtaLabel(panel, "Finding the best route", true);
  try {
    ctx.lastQuote = await ctx.adapter.getQuote(params, ctx.cfg);
    if (quoteIsEmpty(ctx.lastQuote)) {
      setPanelStatus(
        panel,
        "No route available for this swap. Try a different amount or asset.",
        true
      );
      if (btn) btn.disabled = true;
      setCtaLabel(panel, "No route available");
      return;
    }
    renderQuote(panel, ctx.lastQuote);
    var affordErr = affordabilityError(panel, ctx.lastQuote);
    if (affordErr) {
      setPanelStatus(panel, affordErr, true);
      if (btn) btn.disabled = true;
      setCtaLabel(panel, shortfallLabel(panel));
      return;
    }
    setPanelStatus(panel, "");
    applyOwnership(panel, walletOwns(ctx.fromAddress));
    scheduleRequote(panel, ctx);
  } catch (e) {
    setPanelStatus(panel, "Could not fetch a quote: " + (e && e.message), true);
    if (btn) btn.disabled = true;
    setCtaLabel(panel, "Quote unavailable");
  }
}

/** "Not enough USDC" for the source the user cannot cover. */
function shortfallLabel(panel) {
  var sel = panel.querySelector(".id-swap-from");
  var opt = sel && sel.options[sel.selectedIndex];
  var unit = (opt && opt.dataset.unit) || "";
  return unit ? "Not enough " + unit : "Not enough to cover this";
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
  var btn = panel.querySelector(".id-swap-swap-btn");
  if (btn) btn.disabled = true;
  var submitted = false;
  // Hold the automatic re-pricing: swapping the quote out from under a group
  // that is already being built is the one moment it must not happen.
  ctx.swapping = true;
  clearTimeout(ctx.requoteTimer);
  setPanelStatus(panel, "Re-checking balance…");
  setCtaLabel(panel, "Re-checking balance", true);
  try {
    var fresh = await fetchHoldings(ctx.holdingsUrl);
    var from = fresh.filter(function (h) {
      return Number(h.id) === params.fromAssetId;
    })[0];
    var requiredInput =
      ctx.lastQuote.mode === "buy" ? ctx.lastQuote.maximumSent : params.amount;
    if (!from || BigInt(from.amount) < requiredInput) {
      setPanelStatus(panel, "Insufficient balance — it may have changed.", true);
      setCtaLabel(panel, shortfallLabel(panel));
      return;
    }
    var txid;
    if (typeof ctx.adapter.executeSwap === "function") {
      // Router owns build + opt-in + sign + submit (e.g. Haystack's composer).
      setPanelStatus(panel, "Awaiting signature…");
      setCtaLabel(panel, "Check your wallet", true);
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
      setCtaLabel(panel, "Building transaction", true);
      var group = await ctx.adapter.buildSwapGroup(
        ctx.lastQuote,
        ctx.fromAddress,
        ctx.cfg
      );
      if (!Array.isArray(group)) {
        if (typeof window.asastatsSwap.signAndSendPartial !== "function") {
          throw new Error("The connected wallet does not support quote-signed groups");
        }
        setPanelStatus(panel, "Awaiting signature…");
        setCtaLabel(panel, "Check your wallet", true);
        txid = await window.asastatsSwap.signAndSendPartial(group);
        renderSwapSuccess(panel, txid);
        markSwapDirty(panel);
        submitted = true;
        return;
      }
      var userNeedsOptIn = !isOptedIn(fresh, params.toAssetId);
      setPanelStatus(
        panel,
        userNeedsOptIn || (ctx.cfg && ctx.cfg.referrer)
          ? "Awaiting signature (may include opt-in)…"
          : "Awaiting signature…"
      );
      setCtaLabel(panel, "Check your wallet", true);
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
    setCtaLabel(panel, "Try again");
  } finally {
    ctx.swapping = false;
    // Keep the button disabled after a successful submit (the amount was
    // cleared); on failure, restore it to the owner's normal state.
    if (btn) btn.disabled = submitted || !ctx.owns;
    if (submitted) setCtaLabel(panel, "Swap submitted");
    else if (btn) btn.classList.remove("is-busy");
  }
}

/**
 * A short exchange rate ("0.23368") from the two sides of a quote, or "" when
 * there isn't one to state. Both sides are optional: an adapter is free to
 * return only the side it computed, and a missing rate costs a line of text
 * whereas a thrown BigInt conversion costs the whole panel.
 */
function rateBetween(amountIn, inDecimals, amountOut, outDecimals) {
  if (amountIn == null || amountOut == null) return "";
  var paid = Number(baseUnitsToDecimal(amountIn, inDecimals));
  var got = Number(baseUnitsToDecimal(amountOut, outDecimals));
  if (!paid || !got || !isFinite(paid) || !isFinite(got)) return "";
  var rate = got / paid;
  // Six significant figures reads the same for a 20,000:1 pair as for a 1:1 one.
  return String(Number(rate.toPrecision(6)));
}

/** The severity class for a price impact, or "" when there is nothing to warn about. */
function impactSeverity(pct) {
  if (pct >= 3) return "bad";
  if (pct >= 1) return "warn";
  return "good";
}

/** One <dt>/<dd> pair in the quote's detail list. */
function quoteRow(label, value, severity) {
  var row = document.createElement("div");
  row.className = "swap-drow";
  var dt = document.createElement("dt");
  dt.textContent = label;
  var dd = document.createElement("dd");
  if (severity) dd.className = severity;
  if (typeof value === "string") dd.textContent = value;
  else dd.appendChild(value);
  row.appendChild(dt);
  row.appendChild(dd);
  return row;
}

/** The route as one pill per venue, carrying the split when the router gave one. */
function routePills(q) {
  var wrap = document.createElement("div");
  wrap.className = "swap-hops";
  var parts = q.routeParts && q.routeParts.length
    ? q.routeParts
    : routePartsFromNames(
        String(q.routeLabel || "")
          .split(",")
          .map(function (s) { return s.trim(); })
          .filter(Boolean)
      );
  parts.forEach(function (part) {
    var pill = document.createElement("span");
    pill.className = "swap-hop";
    pill.appendChild(document.createTextNode(part.name));
    if (part.pct != null) {
      var pct = document.createElement("i");
      pct.textContent = Number(Number(part.pct).toFixed(1)) + "%";
      pill.appendChild(pct);
    }
    wrap.appendChild(pill);
  });
  return wrap;
}

/**
 * Render the quote as a table rather than a sentence.
 *
 * The computed side -- what you receive on a sell, what you must spend on a buy
 * -- is mirrored into the leg's read-only amount field, so the number the user
 * is actually deciding on is the largest thing on screen instead of a clause in
 * the middle of a string. Everything that qualifies it (the slippage bound, the
 * impact, the fee, the venues) sits under a rate line that can be collapsed.
 *
 * Built with createElement throughout: asset units and venue names come from the
 * engine and the routers, and none of them are escaped on the way in.
 */
function renderQuote(panel, q) {
  var out = panel.querySelector(".id-swap-quote");
  if (!out) return;
  var fromSel = panel.querySelector(".id-swap-from");
  var fromOpt = fromSel && fromSel.options[fromSel.selectedIndex];
  var fromDec = Number((fromOpt && fromOpt.dataset.decimals) || "0");
  var fromUnit = (fromOpt && fromOpt.dataset.unit) || "";
  var toHidden = panel.querySelector(".id-swap-to");
  var toDec = Number((toHidden && toHidden.dataset.decimals) || "0");
  var toUnit = (toHidden && toHidden.dataset.unit) || "";
  var buy = q.mode === "buy";

  // Mirror the computed side into the other leg's read-only field.
  var computed = buy
    ? baseUnitsToDecimal(q.amountIn, fromDec)
    : baseUnitsToDecimal(q.amountOut, toDec);
  var outField = panel.querySelector(".id-swap-out");
  if (outField) outField.value = computed;

  out.textContent = "";

  // --- summary: the rate, a freshness ring, and the disclosure control -------
  var summary = document.createElement("button");
  summary.type = "button";
  summary.className = "swap-quote-sum";
  summary.setAttribute("aria-expanded", panel.dataset.quoteOpen === "1" ? "true" : "false");

  var ring = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  ring.setAttribute("class", "swap-fresh");
  ring.setAttribute("viewBox", "0 0 20 20");
  ring.setAttribute("aria-hidden", "true");
  ["track", "head"].forEach(function (role) {
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("class", "swap-fresh-" + role);
    c.setAttribute("cx", "10");
    c.setAttribute("cy", "10");
    c.setAttribute("r", "7.5");
    c.setAttribute("fill", "none");
    if (role === "head") {
      c.setAttribute("stroke-linecap", "round");
      c.setAttribute("transform", "rotate(-90 10 10)");
      c.setAttribute("stroke-dasharray", "47.1");
    }
    ring.appendChild(c);
  });
  summary.appendChild(ring);

  var rate = rateBetween(q.amountIn, fromDec, q.amountOut, toDec);
  var rateEl = document.createElement("span");
  rateEl.className = "swap-quote-rate";
  rateEl.textContent = rate
    ? "1 " + fromUnit + " = " + rate + " " + toUnit
    : "Quote ready";
  summary.appendChild(rateEl);

  var chev = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  chev.setAttribute("class", "swap-chev");
  chev.setAttribute("viewBox", "0 0 24 24");
  chev.setAttribute("aria-hidden", "true");
  var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "m6 9 6 6 6-6");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2.4");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  chev.appendChild(path);
  summary.appendChild(chev);
  out.appendChild(summary);

  // --- details --------------------------------------------------------------
  var details = document.createElement("dl");
  details.className = "swap-quote-det";
  details.appendChild(
    buy
      ? quoteRow("Maximum sent", baseUnitsToDecimal(q.maximumSent, fromDec) + " " + fromUnit)
      : quoteRow(
          "Minimum received",
          baseUnitsToDecimal(q.minimumReceived, toDec) + " " + toUnit
        )
  );
  if (q.priceImpactPct != null) {
    var impact = Number(q.priceImpactPct);
    details.appendChild(
      quoteRow("Price impact", impact.toFixed(2) + "%", impactSeverity(impact))
    );
  }
  details.appendChild(
    quoteRow("Network fee", baseUnitsToDecimal(BigInt(q.feesTotal), 6) + " ALGO")
  );
  details.appendChild(quoteRow("Route", routePills(q)));
  out.appendChild(details);

  out.dataset.open = panel.dataset.quoteOpen === "1" ? "1" : "0";
  renderVenueCount(panel, q);
}

/** Name the breadth of the search in the modal footer, from the quote itself. */
function renderVenueCount(panel, q) {
  var modal = panel.closest && panel.closest(".swap-modal");
  var el = modal && modal.querySelector(".id-swap-venues");
  if (!el) return;
  var count = (q && q.routeParts && q.routeParts.length) || 0;
  el.textContent = count
    ? "Best route across " + count + (count === 1 ? " venue" : " venues")
    : "";
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
    var sel = panel.querySelector(".id-swap-from");
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
  var sel = panel.querySelector(".id-swap-from");
  var maxEl = panel.querySelector(".id-swap-from-max");
  if (!sel || !maxEl) return;
  var opt = sel.options[sel.selectedIndex];
  if (!opt || opt.dataset.amount === undefined) {
    maxEl.textContent = "";
    return;
  }
  var dec = Number(opt.dataset.decimals || "0");
  var unit = opt.dataset.unit || "";
  // Sits in the leg header under a "Balance" label, so it states the holding and
  // nothing else -- the em dash it used to carry belonged to the old sentence.
  maxEl.textContent =
    baseUnitsToDecimal(BigInt(opt.dataset.amount), dec) + (unit ? " " + unit : "");
}

function clearQuote(panel) {
  var el = panel.querySelector(".id-swap-quote");
  if (el) el.textContent = "";
  // The computed leg is part of the quote: leaving a stale figure in it while
  // the new one is in flight is worse than showing nothing.
  var outField = panel.querySelector(".id-swap-out");
  if (outField) outField.value = "";
  renderVenueCount(panel, null);
}

/**
 * Label the primary action with the next step, without touching whether it is
 * enabled -- that stays with the caller that knows (applyOwnership, refreshQuote,
 * executeSwap), so a label change can never accidentally arm the button.
 */
function setCtaLabel(panel, label, busy) {
  var btn = panel.querySelector(".id-swap-swap-btn");
  if (!btn) return "";
  btn.classList.toggle("is-busy", !!busy);
  btn.textContent = "";
  if (busy) {
    var spinner = document.createElement("span");
    spinner.className = "swap-spinner";
    btn.appendChild(spinner);
  }
  btn.appendChild(document.createTextNode(label));
  return label;
}

/**
 * What the primary action should say right now: the step still missing, or the
 * swap it is about to perform. Naming the next step on the button is the whole
 * point -- a disabled control labelled "Swap" tells the user nothing.
 */
function ctaLabelFor(panel) {
  var to = panel.querySelector(".id-swap-to");
  var amount = panel.querySelector(".id-swap-amount");
  if (!to || !to.value) return "Select a token";
  if (!amount || !amount.value) return "Enter an amount";
  return to.dataset.optedIn === "0" ? "Opt in and swap" : "Swap";
}

function setPanelStatus(panel, msg, isError) {
  var el = panel.querySelector(".id-swap-status");
  if (el) {
    el.textContent = msg;
    el.classList.toggle("id-swap-status-error", !!isError);
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
  var sel = panel.querySelector(".id-swap-from");
  if (!sel) return false;
  var match = sel.querySelector('option[value="' + fromAsset + '"]');
  if (!match) return false;
  sel.value = fromAsset;
  return true;
}

/** Read the router cfg island the holdings partial embeds (`.id-swap-cfg`). */
function readPanelCfg(panelEl) {
  var el = panelEl.querySelector(".id-swap-cfg");
  if (!el) return null;
  return {
    router: el.dataset.router || "",
    network: el.dataset.network || "mainnet",
    referrer: el.dataset.referrer || "",
    feeBps: Number(el.dataset.feeBps || "0"),
    explorerBase: el.dataset.explorerBase || "",
    explorerTxPath: el.dataset.explorerTxPath || "",
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
    baseUrl: marker.dataset.baseUrl || "",
    quoteUrl: marker.dataset.quoteUrl || "",
    groupUrl: marker.dataset.groupUrl || "",
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
  var sel = panel.querySelector(".id-swap-from");
  if (!sel || !sel.value) return null;
  var opt = sel.options[sel.selectedIndex];
  if (!opt || opt.dataset.amount === undefined) return null;
  return BigInt(opt.dataset.amount || "0");
}

/**
 * ALGO this swap needs the account to keep back, in base units.
 *
 * The engine already nets the minimum balance out of the ALGO holding --
 * `utils.clients._address_assets` stores `amount - min-balance` at id 0 -- so
 * what is left to hold back is what the swap itself costs:
 *
 *   * the group's transaction fees, and
 *   * the 0.1 ALGO an opt-in to a target the account does not hold yet locks
 *     up. That is an INCREASE to the minimum balance, and it does not exist
 *     yet at the moment the engine measures one, so no server-side figure can
 *     account for it. Only the panel knows what is about to be bought.
 *
 * The exact fee arrives with the quote (`feesTotal`), but the percentage chips
 * run before there is one, so this is a deliberate round over-estimate. Being
 * a few hundredths conservative costs the user nothing they will notice; being
 * one fee short fails the whole group after they have signed it.
 */
function algoHeadroomBaseUnits(panel) {
  var to = panel.querySelector(".id-swap-to");
  var optingIn = !!(to && to.value && to.dataset.optedIn !== "1");
  return (
    BigInt(SWAP_FEE_HEADROOM) +
    (optingIn ? BigInt(ASSET_OPTIN_MIN_BALANCE) : BigInt(0))
  );
}

/**
 * The most of `assetId` this swap could actually spend, given a `base` holding.
 *
 * Only ALGO pays the group's fees and the opt-in, so every other asset can be
 * spent to the last base unit. Never returns a negative: an account whose ALGO
 * is already below the headroom can spend none of it, not a negative amount.
 */
function spendableBaseUnits(panel, assetId, base) {
  if (Number(assetId) !== ALGO_ASSET_ID) return base;
  var spendable = base - algoHeadroomBaseUnits(panel);
  return spendable > BigInt(0) ? spendable : BigInt(0);
}

/** Set the amount field to `pct`% of the selected source holding; returns it. */
function setAmountFromPercent(panel, pct) {
  var sel = panel.querySelector(".id-swap-from");
  var amountEl = panel.querySelector(".id-swap-amount");
  var base = sourceHoldingsBaseUnits(panel);
  if (!sel || !amountEl || base === null) return "";
  var opt = sel.options[sel.selectedIndex];
  var decimals = Number((opt && opt.dataset.decimals) || "0");
  // Cap rather than scale: 25/50/75 stay true fractions of what is held, and
  // only the chip that would overshoot -- in practice Max -- is pulled down to
  // what the swap can really spend.
  var wanted = decimalToBaseUnits(applyPercent(base, decimals, pct), decimals);
  var ceiling = spendableBaseUnits(panel, sel.value, base);
  var value = baseUnitsToDecimal(wanted > ceiling ? ceiling : wanted, decimals);
  amountEl.value = value;
  return value;
}

/**
 * Flip the source/target columns between "sell" (default) and "buy".
 *
 * Also moves the one editable amount field into the leg whose amount the user
 * fixes in this mode, and puts the read-only field in the leg it vacates. Moving
 * the element rather than keeping one per leg is what lets `readQuoteParams`
 * stay a single `.id-swap-amount` query: an input keeps its value and its
 * listeners across a re-parent.
 */
function applySwapMode(formEl, mode) {
  if (!formEl) return "sell";
  var buy = mode === "buy";
  formEl.classList.toggle("swap-mode-buy", buy);
  positionAmountField(formEl, buy);
  markModeControls(formEl, buy ? "buy" : "sell");
  return buy ? "buy" : "sell";
}

/** Put .id-swap-amount in the fixed leg and .id-swap-out in the computed one. */
function positionAmountField(formEl, buy) {
  var amount = formEl.querySelector(".id-swap-amount");
  var out = formEl.querySelector(".id-swap-out");
  var paySlot = formEl.querySelector(".id-swap-slot-pay");
  var getSlot = formEl.querySelector(".id-swap-slot-get");
  if (!amount || !out || !paySlot || !getSlot) return false;
  if (buy) {
    getSlot.appendChild(amount);
    paySlot.appendChild(out);
  } else {
    paySlot.appendChild(amount);
    getSlot.appendChild(out);
  }
  return true;
}

/** Reflect the active mode on the segmented control (Materialize no longer does). */
function markModeControls(formEl, mode) {
  // closest() yields an Element or null, and the document stands in for null,
  // so the host always has querySelectorAll -- no guard needed.
  var host = (formEl.closest && formEl.closest(".swap-modal")) || document;
  Array.prototype.forEach.call(
    host.querySelectorAll("[data-swap-mode]"),
    function (tab) {
      tab.setAttribute("aria-selected", String(tab.dataset.swapMode === mode));
    }
  );
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
  var fromSel = panel.querySelector(".id-swap-from");
  var toHidden = panel.querySelector(".id-swap-to");
  var toSearch = panel.querySelector(".id-swap-to-search");
  var anchorId = panel.dataset.anchorId || fromSel.value || "";
  panel.dataset.anchorId = anchorId;
  if (mode === "buy") {
    var anchorOpt = fromSel.querySelector('option[value="' + anchorId + '"]');
    // Lock the target (To) to the anchor -- the asset being bought.
    toHidden.value = anchorId;
    toHidden.dataset.decimals = (anchorOpt && anchorOpt.dataset.decimals) || "0";
    toHidden.dataset.unit = (anchorOpt && anchorOpt.dataset.unit) || "";
    toHidden.dataset.icon = (anchorOpt && anchorOpt.dataset.icon) || "";
    toHidden.dataset.optedIn = "1"; // the anchor is held, so already opted in
    panel.querySelector(".id-swap-optin-notice").style.display = "none";
    var anchorUnit = (anchorOpt && anchorOpt.dataset.unit) || "asset";
    // Leave the search box EMPTY so typing searches cleanly; advertise the default
    // buy target in the placeholder. The actual default selection lives in the
    // hidden input, so a quote works with no further interaction, and the user can
    // type to pick a different asset to buy.
    toSearch.value = "";
    toSearch.placeholder =
      "Buying " + anchorUnit + " (#" + anchorId + ") — type to change";
    panel.querySelector(".id-swap-to-results").innerHTML = "";
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
    syncAssetButtons(panel);
    return { mode: "buy", ok: true };
  }
  // Sell: the anchor is the From again; the To returns to a free search picker.
  fromSel.value = anchorId;
  toHidden.value = "";
  toHidden.dataset.decimals = "";
  toHidden.dataset.unit = "";
  toHidden.dataset.icon = "";
  toHidden.dataset.optedIn = "";
  toSearch.value = "";
  toSearch.placeholder = "Search name, unit or asset ID";
  panel.querySelector(".id-swap-optin-notice").style.display = "none";
  syncAssetButtons(panel);
  return { mode: "sell", ok: true };
}

/**
 * Explorer transaction URL for a txid. Defaults to Allo (the historical
 * provider) when no base/path is supplied, so callers and tests that don't pass
 * a provider keep their old behaviour. ``base`` is a trailing-slash provider
 * root and ``path`` the transaction path segment (e.g. "tx/" for Allo,
 * "transaction/" for Lora).
 */
function txExplorerUrl(txid, base, path) {
  base = base || "https://allo.info/";
  path = path || "tx/";
  return base + path + encodeURIComponent(txid);
}

/**
 * Render a successful submission: a tappable allo.info link for the txid, then
 * reset the form to a clean state (clear amount + percentage + the now-stale
 * quote). The Swap button is left for executeSwap to disable, since the cleared
 * amount means there's nothing valid to re-submit.
 */
function renderSwapSuccess(panel, txid) {
  var status = panel.querySelector(".id-swap-status");
  if (status) {
    status.classList.remove("id-swap-status-error");
    status.textContent = "Swap submitted: ";
    var a = document.createElement("a");
    a.className = "id-swap-tx-link";
    var cfg = readPanelCfg(panel) || {};
    var base = cfg.explorerBase;
    var path = cfg.explorerTxPath;
    if (!base) {
      var root =
        (panel.closest && panel.closest("#id-swap-swap")) ||
        document.getElementById("id-swap-swap");
      if (root) {
        base = root.dataset.explorerBase;
        path = path || root.dataset.explorerTxPath;
      }
    }
    a.href = txExplorerUrl(txid, base, path);
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = txid;
    status.appendChild(a);
  }
  var amount = panel.querySelector(".id-swap-amount");
  if (amount) amount.value = "";
  var pct = panel.querySelector(".id-swap-pct");
  if (pct) pct.value = "";
  var quote = panel.querySelector(".id-swap-quote");
  if (quote) quote.textContent = "";
  var outField = panel.querySelector(".id-swap-out");
  if (outField) outField.value = "";
}

/**
 * Flag the enclosing modal "dirty" after a successful swap so closing it can
 * refresh now-stale holdings on the parent page. Returns whether a modal was
 * found (no-op on the shell accordion, which has no modal).
 */
function markSwapDirty(panel) {
  var modal = panel.closest && panel.closest(".swap-modal");
  if (modal) modal.dataset.swapDirty = "1";
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
  var btn = panel.querySelector(".id-swap-swap-btn");
  if (btn) btn.disabled = !owns;
  var notice = panel.querySelector(".id-swap-connect-notice");
  if (notice) notice.style.display = owns ? "none" : "block";
  setCtaLabel(panel, owns ? ctaLabelFor(panel) : "Connect wallet to swap");
  return !!owns;
}

/* ------------------------------------------------------------------ pills */

/**
 * Paint one asset pill. The `<select>` and the hidden target input remain the
 * source of truth for every other function; these buttons only display them, so
 * nothing here can put the panel into a state the controller cannot read back.
 */
function setAssetPill(panel, side, unit, icon) {
  var btn = panel.querySelector(".id-swap-" + side + "-btn");
  var label = panel.querySelector(".id-swap-" + side + "-unit");
  if (!btn || !label) return false;
  var chosen = !!unit;
  label.textContent = chosen
    ? unit
    : side === "from"
      ? "Select"
      : "Select token";
  btn.classList.toggle("swap-assetbtn-empty", !chosen);
  var img = panel.querySelector(".id-swap-" + side + "-icon");
  if (img) {
    var fallback = img.dataset.fallback || "";
    var next = chosen && icon ? icon : fallback;
    if (img.getAttribute("src") !== next) img.setAttribute("src", next);
  }
  return chosen;
}

/** Mirror the current source + target selections into both pills. */
function syncAssetButtons(panel) {
  var sel = panel.querySelector(".id-swap-from");
  var opt = sel && sel.options[sel.selectedIndex];
  setAssetPill(
    panel,
    "from",
    opt ? opt.dataset.unit || String(opt.value) : "",
    opt ? opt.dataset.icon : ""
  );
  var to = panel.querySelector(".id-swap-to");
  var hasTarget = !!(to && to.value);
  setAssetPill(
    panel,
    "to",
    hasTarget ? to.dataset.unit || "#" + to.value : "",
    to ? to.dataset.icon : ""
  );
  var flip = panel.querySelector(".id-swap-flip");
  if (flip) {
    var able = canFlipAssets(panel);
    flip.disabled = !able;
    flip.title = able
      ? "Swap the two assets"
      : "You can only swap into this direction from an asset you hold";
  }
  return hasTarget;
}

/* ----------------------------------------------------------------- picker */

/** Format one holding row for the source picker. */
function ownedRow(option, selected) {
  var li = document.createElement("li");
  li.className = "swap-row id-swap-own-option";
  li.dataset.id = option.value;
  if (selected) li.classList.add("is-selected");

  var img = document.createElement("img");
  img.className = "swap-tok";
  img.alt = "";
  if (option.dataset.icon) img.src = option.dataset.icon;
  li.appendChild(img);

  var text = document.createElement("span");
  text.className = "swap-row-text";
  var unit = document.createElement("span");
  unit.className = "swap-row-unit";
  unit.textContent = option.dataset.unit || option.value;
  var pill = document.createElement("span");
  pill.className = "swap-idpill swap-num";
  pill.textContent = "#" + option.value;
  unit.appendChild(pill);
  text.appendChild(unit);
  var name = document.createElement("span");
  name.className = "swap-row-name";
  name.textContent = option.dataset.name || "";
  text.appendChild(name);
  li.appendChild(text);

  var bal = document.createElement("span");
  bal.className = "swap-row-bal swap-num";
  bal.textContent = baseUnitsToDecimal(
    BigInt(option.dataset.amount || "0"),
    Number(option.dataset.decimals || "0")
  );
  li.appendChild(bal);
  return li;
}

/**
 * Render the holdings the address can spend, straight from the `<select>`. No
 * round trip: this list is the same data the panel was already delivered with.
 * The current target is left out, since an asset cannot be swapped for itself.
 */
function renderOwnedList(panel) {
  var host = panel.querySelector(".id-swap-own-results");
  var sel = panel.querySelector(".id-swap-from");
  if (!host || !sel) return 0;
  var to = panel.querySelector(".id-swap-to");
  var excluded = to ? to.value : "";
  host.textContent = "";
  var list = document.createElement("ul");
  list.className = "swap-rows";
  var shown = 0;
  for (var i = 0; i < sel.options.length; i++) {
    var option = sel.options[i];
    if (excluded && option.value === excluded) continue;
    list.appendChild(ownedRow(option, option.value === sel.value));
    shown += 1;
  }
  if (!shown) {
    var empty = document.createElement("p");
    empty.className = "swap-row-empty";
    empty.textContent = "You hold nothing else to spend on this swap.";
    host.appendChild(empty);
    return 0;
  }
  host.appendChild(list);
  return shown;
}

/** Open the picker sheet over the panel for the given side ("from"/"to"). */
function openAssetPicker(panel, side) {
  var picker = panel.querySelector(".id-swap-picker");
  if (!picker) return false;
  picker.dataset.side = side;
  picker.hidden = false;
  var title = panel.querySelector(".id-swap-picker-title");
  if (title) {
    title.textContent =
      side === "from" ? "Select a token to pay with" : "Select a token to receive";
  }
  if (side === "from") renderOwnedList(panel);
  var search = panel.querySelector(".id-swap-to-search");
  if (side === "to" && search && search.focus) search.focus();
  return true;
}

function closeAssetPicker(panel) {
  var picker = panel.querySelector(".id-swap-picker");
  if (picker) picker.hidden = true;
}

/** Choose the source asset, keeping the `<select>` authoritative. */
function selectSource(panel, assetId) {
  var sel = panel.querySelector(".id-swap-from");
  if (!sel) return false;
  var option = sel.querySelector('option[value="' + assetId + '"]');
  if (!option) return false;
  sel.value = assetId;
  // In Sell the source IS the anchor, so a deliberate pick re-anchors the panel;
  // otherwise switching to Buy and back would snap to the asset first clicked.
  var form = panel.querySelector(".id-swap-form");
  if (!form || !form.classList.contains("swap-mode-buy")) {
    panel.dataset.anchorId = String(assetId);
  }
  syncAssetButtons(panel);
  updateSourceMax(panel);
  closeAssetPicker(panel);
  return true;
}

/* ------------------------------------------------------------------- flip */

/**
 * Whether the two sides can trade places. The source has to be something the
 * address actually holds, so a target that isn't in the holdings cannot become
 * one -- the control says so up front instead of failing at quote time.
 */
function canFlipAssets(panel) {
  var sel = panel.querySelector(".id-swap-from");
  var to = panel.querySelector(".id-swap-to");
  if (!sel || !to || !to.value) return false;
  return !!sel.querySelector('option[value="' + to.value + '"]');
}

/** Trade the two sides over: sell back what you just bought. */
function flipAssets(panel) {
  if (!canFlipAssets(panel)) return false;
  var sel = panel.querySelector(".id-swap-from");
  var to = panel.querySelector(".id-swap-to");
  var wasFrom = sel.options[sel.selectedIndex];
  var nextFrom = to.value;

  to.value = wasFrom ? wasFrom.value : "";
  to.dataset.decimals = (wasFrom && wasFrom.dataset.decimals) || "0";
  to.dataset.unit = (wasFrom && wasFrom.dataset.unit) || "";
  to.dataset.icon = (wasFrom && wasFrom.dataset.icon) || "";
  // It was a holding a moment ago, so the account is opted in by definition.
  to.dataset.optedIn = "1";

  sel.value = nextFrom;
  panel.dataset.anchorId = String(nextFrom);

  var notice = panel.querySelector(".id-swap-optin-notice");
  if (notice) notice.style.display = "none";
  var search = panel.querySelector(".id-swap-to-search");
  if (search) {
    search.value = "";
    search.placeholder = "Search name, unit or asset ID";
  }
  var results = panel.querySelector(".id-swap-to-results");
  if (results) results.innerHTML = "";

  syncAssetButtons(panel);
  updateSourceMax(panel);
  return true;
}

/* -------------------------------------------------------------- slippage */

/** The advice for a tolerance that will cost the user something either way. */
function slippageWarning(value) {
  if (value >= 5) {
    return (
      "At " + value + "% a swap can fill far below the price you were quoted."
    );
  }
  if (value > 0 && value < 0.1) {
    return "Below 0.1% most swaps fail before they confirm, and you pay the fee anyway.";
  }
  return "";
}

/**
 * Set the tolerance from the modal header. The value the controller reads stays
 * the hidden `.id-swap-slippage` input inside the panel, so `readQuoteParams`
 * remains one panel-scoped query; this writes it and lets the panel's own
 * `input` listener re-quote.
 */
function applySlippage(modal, value, quiet) {
  if (!modal) return 0.5;
  var next = Number(value);
  if (isNaN(next) || next < 0) next = 0.5;
  modal.dataset.slippage = String(next);

  var label = modal.querySelector(".id-swap-slip-value");
  if (label) label.textContent = next + "%";
  Array.prototype.forEach.call(
    modal.querySelectorAll(".id-swap-slip-preset"),
    function (chip) {
      chip.setAttribute(
        "aria-pressed",
        String(Number(chip.dataset.slippage) === next)
      );
    }
  );
  var warn = modal.querySelector(".id-swap-slip-warn");
  if (warn) {
    var message = slippageWarning(next);
    warn.hidden = !message;
    warn.textContent = message;
  }
  var input = modal.querySelector(".id-swap-slippage");
  if (input && input.value !== String(next)) {
    input.value = String(next);
    // `quiet` is for a freshly loaded panel: adopt the tolerance without asking
    // for a quote the user hasn't given us the fields for yet.
    if (!quiet) input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  return next;
}

/* istanbul ignore next -- DOM event wiring; logic is covered via applyImpliedSource, applyPercent/setAmountFromPercent, and the scheduleQuote/selectTarget/executeSwap tests */
function bindPanel(panelEl, ctx) {
  ["id-swap-from", "id-swap-amount", "id-swap-slippage"].forEach(function (cls) {
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
  // A freshly loaded panel adopts the tolerance already showing in the header.
  var modal = panelEl.closest && panelEl.closest(".swap-modal");
  if (modal) applySlippage(modal, modal.dataset.slippage || "0.5", true);
  syncAssetButtons(panelEl);
  // The panel starts in Sell, so seat the amount field in the leg it belongs to.
  positionAmountField(panelEl, false);
  setCtaLabel(panelEl, ctaLabelFor(panelEl));

  panelEl.addEventListener("click", function (ev) {
    var closest = ev.target.closest ? ev.target.closest.bind(ev.target) : null;
    if (!closest) return;

    var opt = closest(".id-swap-asset-option");
    if (opt) { selectTarget(panelEl, opt, ctx); return; }

    var own = closest(".id-swap-own-option");
    if (own) {
      selectSource(panelEl, own.dataset.id);
      scheduleQuote(panelEl, ctx);
      return;
    }

    var pick = closest("[data-swap-pick]");
    if (pick) { openAssetPicker(panelEl, pick.dataset.swapPick); return; }

    if (closest(".id-swap-picker-close")) { closeAssetPicker(panelEl); return; }

    if (closest(".id-swap-flip")) {
      if (flipAssets(panelEl)) scheduleQuote(panelEl, ctx);
      return;
    }

    var summary = closest(".swap-quote-sum");
    if (summary) {
      var open = panelEl.dataset.quoteOpen === "1";
      panelEl.dataset.quoteOpen = open ? "0" : "1";
      summary.setAttribute("aria-expanded", String(!open));
      var quote = panelEl.querySelector(".id-swap-quote");
      if (quote) quote.dataset.open = open ? "0" : "1";
      return;
    }

    var pb = closest(".id-swap-pct-btn");
    if (pb) {
      setAmountFromPercent(panelEl, Number(pb.dataset.pct || "0"));
      scheduleQuote(panelEl, ctx);
    }
  });

  // Asset icons come from the CDN by id; plenty of ASAs have none.
  panelEl.addEventListener(
    "error",
    function (ev) {
      var img = ev.target;
      if (!img || img.tagName !== "IMG") return;
      var fallback = img.dataset.fallback;
      if (fallback && img.getAttribute("src") !== fallback) img.src = fallback;
    },
    true
  );

  var pctInput = panelEl.querySelector(".id-swap-pct");
  if (pctInput) {
    pctInput.addEventListener("input", function () {
      setAmountFromPercent(panelEl, Number(pctInput.value || "0"));
      scheduleQuote(panelEl, ctx);
    });
  }
  applyOwnership(panelEl, ctx.owns);
  var btn = panelEl.querySelector(".id-swap-swap-btn");
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
  // Native <details> rather than a framework accordion: `toggle` fires only on
  // a real state change, so this loads once, on the first open, without the
  // click handler having to work out whether the section is opening or closing.
  var section = li.querySelector("details");
  var panelEl = li.querySelector(".id-swap-panel");
  if (!section || !panelEl) return;
  var loaded = false;
  section.addEventListener("toggle", function () {
    if (loaded || !section.open) return;
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
    ev.target.closest && ev.target.closest(".id-swap-swap-toggle");
  if (!btn) return;
  // Inline reveal owns the click; never navigate to the fallback href.
  ev.preventDefault();
  var wrap = document.getElementById(btn.dataset.swapTarget);
  if (!wrap) return;
  var panelEl = wrap.querySelector(".id-swap-panel");
  var labelEl = btn.querySelector(".swap-label");
  var shown = toggleInlineSwap(wrap, labelEl, {
    show: btn.dataset.labelShow || "Swap",
    hide: btn.dataset.labelHide || "Hide",
  });
  if (!shown || !panelEl || btn.dataset.swapLoaded) return;

  var marker = document.getElementById("id-swap-enabled");
  // Swap from the LINKED address the marker carries (the wallet-authenticated
  // account). Holdings + quote need no live wallet connection -- only the final
  // signature does -- so we never ask the user to reconnect just to look.
  var address = marker ? marker.dataset.address : "";
  if (!marker || !address) {
    panelEl.innerHTML =
      '<div class="id-swap-status id-swap-status-error">Swap is not available for this address.</div>';
    return;
  }
  btn.dataset.swapLoaded = "1";
  var from = btn.dataset.from || panelEl.dataset.from;
  loadPanel(panelEl, {
    fromAddress: address,
    owns: walletOwns(address),
    holdingsUrl: inlineHoldingsUrl(marker.dataset.holdingsTmpl, address, from),
    from: from,
    quoteTimer: null,
  });
}

/** Dismiss the swap dialog, if one is open. */
function closeSwapModal() {
  var modal = document.getElementById("swap-modal");
  if (modal && modal.close && modal.open) modal.close();
  return !!modal;
}

/* istanbul ignore next -- DOM/modal glue; the quote + percent + mode logic is unit-tested */
function openSwapModal(fromAsset) {
  var modal = document.getElementById("swap-modal");
  var marker = document.getElementById("id-swap-enabled");
  if (!modal) return;
  // showModal() gives the top layer, the backdrop and a focus trap for free.
  // Guarded because jsdom only grew <dialog> support recently.
  if (modal.showModal && !modal.open) modal.showModal();
  var cfg = markerCfg(marker);
  var address = marker ? marker.dataset.address || "" : "";
  var panelEl = modal.querySelector(".id-swap-panel");
  if (!panelEl) return;
  // Resolve the adapter + cfg from the marker, NOT from the loaded partial: a
  // quote must never fail just because the holdings island lacks router config.
  if (!cfg || !cfg.router || !ROUTERS[cfg.router] || !address) {
    panelEl.innerHTML =
      '<div class="id-swap-status id-swap-status-error">Swap is not available for this address.</div>';
    return;
  }
  if (panelEl.dataset.swapFrom === String(fromAsset) && panelEl.dataset.swapLoaded) {
    return;
  }
  panelEl.dataset.swapFrom = String(fromAsset || "");
  panelEl.dataset.swapLoaded = "1";
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

/* istanbul ignore next -- boot-time query glue; openSwapModal is unit-tested */
function autoOpenFromQuery() {
  var params = new URLSearchParams(window.location.search);
  var fromAsset = params.get("swap_open");
  if (!fromAsset) return;
  // Strip the param first so a refresh doesn't reopen the modal.
  params.delete("swap_open");
  var query = params.toString();
  window.history.replaceState(
    {},
    document.title,
    window.location.pathname + (query ? "?" + query : "") + window.location.hash
  );
  // Reuse the exact click path: openSwapModal reads the #id-swap-enabled marker,
  // so an address that isn't the viewer's shows the standard disabled state.
  openSwapModal(fromAsset);
}

/* istanbul ignore next -- delegated DOM glue; opens the modal for the clicked row */
function handleSwapModalClick(ev) {
  var btn = ev.target.closest && ev.target.closest(".id-swap-swap-toggle");
  if (!btn) return;
  ev.preventDefault(); // the href is a no-JS fallback only
  openSwapModal(btn.dataset.from || "");
}

/* istanbul ignore next -- tab glue; the layout flip itself is unit-tested via applySwapMode */
function wireSwapTabs() {
  var modal = document.getElementById("swap-modal");
  if (!modal) return;
  modal.addEventListener("click", function (ev) {
    var tab = ev.target.closest && ev.target.closest("[data-swap-mode]");
    if (!tab) return;
    applySwapMode(modal.querySelector(".id-swap-form"), tab.dataset.swapMode);
    closeAssetPicker(modal);
    // The amount's meaning flips with the mode (source vs target), so clear the
    // amount + percentage + stale quote and re-gate the button until a fresh,
    // mode-correct quote arrives.
    var panel = modal.querySelector(".id-swap-panel");
    if (!panel) return;
    // Re-target the anchor: From on Sell, To on Buy (and pick a source to spend).
    var res = retargetForMode(panel, tab.dataset.swapMode);
    updateSourceMax(panel);
    var amt = panel.querySelector(".id-swap-amount");
    var pct = panel.querySelector(".id-swap-pct");
    var quote = panel.querySelector(".id-swap-quote");
    var status = panel.querySelector(".id-swap-status");
    var btn = panel.querySelector(".id-swap-swap-btn");
    if (amt) amt.value = "";
    if (pct) pct.value = "";
    if (quote) quote.textContent = "";
    var outField = panel.querySelector(".id-swap-out");
    if (outField) outField.value = "";
    syncAssetButtons(panel);
    setCtaLabel(panel, ctaLabelFor(panel));
    if (status) {
      status.textContent = res.ok
        ? ""
        : "You hold no other assets to spend on a buy.";
    }
    if (btn) btn.disabled = true;
  });
}

/* istanbul ignore next -- entry-point wiring */
function mainSwap() {
  var root = document.getElementById("id-swap-swap");
  if (!root) return;
  var adapter = ROUTERS[root.dataset.router];
  if (!adapter) return;
  var cfg = swapConfig(root);
  var active =
    window.asastatsSwap && window.asastatsSwap.activeAddress
      ? window.asastatsSwap.activeAddress()
      : null;
  var items = root.querySelectorAll("#id-swap-addresses > li");
  Array.prototype.forEach.call(items, function (li) {
    wireSection(li, adapter, cfg, active);
  });
}

/* istanbul ignore next -- bridge-readiness gate */
function startSwap() {
  // Swap buttons open a modal. One delegated listener, attached as soon as this
  // script runs; the marker (router + cfg + linked address) is read at click
  // time, so this needs neither the bridge nor htmx swap timing to be ready.
  document.addEventListener("click", handleSwapModalClick);
  var modal = document.getElementById("swap-modal");
  if (modal) {
    // A native <dialog>: the browser owns opening, the backdrop, focus capture
    // and Escape, so there is no framework component to initialise here.
    modal.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest(".id-swap-close")) closeSwapModal();
    });
    // After a successful swap the viewed holdings are stale; refresh the parent
    // page when the user closes the modal -- but only if a swap actually marked
    // it dirty, so a look-and-cancel never reloads. `close` fires however the
    // dialog was dismissed, Escape included, which the old handler missed.
    modal.addEventListener("close", function () {
      if (modal.dataset.swapDirty === "1") window.location.reload();
    });
  }
  wireSwapTabs();
  wireSlippage();
  // Shell page (accordion of addresses) binds per-section once the bridge is up.
  whenSwapReady(mainSwap);
  // Auto-open (post-login ?swap_open) must wait for the bridge too, so the
  // panel's initial `owns` reads the resumed wallet session, not a null one.
  whenSwapReady(autoOpenFromQuery);
}

/**
 * Wire the header's tolerance control. It lives in the modal shell rather than
 * the panel so it survives the panel being replaced (or failing to load), and
 * writes through to the hidden input the panel owns.
 */
/* istanbul ignore next -- modal-level DOM glue; applySlippage carries the logic */
function wireSlippage() {
  var modal = document.getElementById("swap-modal");
  if (!modal) return;
  applySlippage(modal, modal.dataset.slippage || "0.5", true);

  var toggle = modal.querySelector(".id-swap-slip-toggle");
  var popover = modal.querySelector("#swap-slippage-pop");
  if (toggle && popover) {
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      popover.hidden = open;
    });
  }
  modal.addEventListener("click", function (ev) {
    var chip = ev.target.closest && ev.target.closest(".id-swap-slip-preset");
    if (!chip) return;
    var custom = modal.querySelector(".id-swap-slip-custom");
    if (custom) custom.value = "";
    applySlippage(modal, chip.dataset.slippage);
  });
  var custom = modal.querySelector(".id-swap-slip-custom");
  if (custom) {
    custom.addEventListener("input", function () {
      var typed = parseFloat(custom.value);
      if (!isNaN(typed)) applySlippage(modal, typed);
    });
  }
}

/**
 * Run `fn` once the swap bridge is available: immediately if it already is,
 * otherwise on the next `asastats:swap-ready`. The bridge publishes
 * `window.asastatsSwap` and dispatches that event only after the wallet manager
 * resumes, so anything reading `walletOwns`/`activeAddress` must wait for it.
 */
function whenSwapReady(fn) {
  if (window.asastatsSwap) {
    fn();
  } else {
    window.addEventListener("asastats:swap-ready", fn, { once: true });
  }
}

/* istanbul ignore else -- in the browser we self-start; under jest we export */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    FolksAdapter: FolksAdapter,
    HaystackAdapter: HaystackAdapter,
    AsastatsAdapter: AsastatsAdapter,
    HogswapAdapter: HogswapAdapter,
    ROUTERS: ROUTERS,
    makeQuote: makeQuote,
    routeLabelFrom: routeLabelFrom,
    routePartsFrom: routePartsFrom,
    routePartsFromNames: routePartsFromNames,
    rateBetween: rateBetween,
    impactSeverity: impactSeverity,
    routePills: routePills,
    renderVenueCount: renderVenueCount,
    setCtaLabel: setCtaLabel,
    ctaLabelFor: ctaLabelFor,
    shortfallLabel: shortfallLabel,
    scheduleRequote: scheduleRequote,
    positionAmountField: positionAmountField,
    markModeControls: markModeControls,
    setAssetPill: setAssetPill,
    syncAssetButtons: syncAssetButtons,
    ownedRow: ownedRow,
    renderOwnedList: renderOwnedList,
    openAssetPicker: openAssetPicker,
    closeAssetPicker: closeAssetPicker,
    selectSource: selectSource,
    canFlipAssets: canFlipAssets,
    flipAssets: flipAssets,
    slippageWarning: slippageWarning,
    applySlippage: applySlippage,
    wireSlippage: wireSlippage,
    minReceived: minReceived,
    maxSent: maxSent,
    quoteIsEmpty: quoteIsEmpty,
    affordabilityError: affordabilityError,
    retargetForMode: retargetForMode,
    updateSourceMax: updateSourceMax,
    swapConfig: swapConfig,
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
    alloTxUrl: txExplorerUrl,
    txExplorerUrl: txExplorerUrl,
    renderSwapSuccess: renderSwapSuccess,
    markSwapDirty: markSwapDirty,
    decimalToBaseUnits: decimalToBaseUnits,
    baseUnitsToDecimal: baseUnitsToDecimal,
    b64ToBytes: b64ToBytes,
    readPanelCfg: readPanelCfg,
    markerCfg: markerCfg,
    applyPercent: applyPercent,
    sourceHoldingsBaseUnits: sourceHoldingsBaseUnits,
    algoHeadroomBaseUnits: algoHeadroomBaseUnits,
    spendableBaseUnits: spendableBaseUnits,
    setAmountFromPercent: setAmountFromPercent,
    SWAP_FEE_HEADROOM: SWAP_FEE_HEADROOM,
    ASSET_OPTIN_MIN_BALANCE: ASSET_OPTIN_MIN_BALANCE,
    applySwapMode: applySwapMode,
    inlineHoldingsUrl: inlineHoldingsUrl,
    toggleInlineSwap: toggleInlineSwap,
    bindPanel: bindPanel,
    loadPanel: loadPanel,
    handleInlineSwapClick: handleInlineSwapClick,
    closeSwapModal: closeSwapModal,
    openSwapModal: openSwapModal,
    autoOpenFromQuery: autoOpenFromQuery,
    whenSwapReady: whenSwapReady,
    handleSwapModalClick: handleSwapModalClick,
    wireSwapTabs: wireSwapTabs,
    wireSection: wireSection,
    mainSwap: mainSwap,
    startSwap: startSwap,
  };
} else {
  /* istanbul ignore next -- browser entry point */
  startSwap();
}
