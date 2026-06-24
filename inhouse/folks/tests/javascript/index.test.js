const F = require("../../static/folks/folks.js");

function panelHTML(holdings) {
  return `
    <div class="id-folks-panel" data-holdings-url="/widgets/folks/A/holdings">
      <script type="application/json" class="id-folks-holdings">${JSON.stringify(holdings)}</script>
      <div class="id-folks-form" data-address="ADDR">
        <select class="id-folks-from">
          <option value="0" data-decimals="6" data-unit="ALGO" data-amount="5000000">ALGO</option>
        </select>
        <input class="id-folks-to-search">
        <div class="id-folks-to-results"></div>
        <input type="hidden" class="id-folks-to" data-decimals="" data-unit="" data-opted-in="">
        <input class="id-folks-amount">
        <input class="id-folks-slippage" value="0.5">
        <div class="id-folks-quote"></div>
        <div class="id-folks-status"></div>
        <div class="id-folks-optin-notice" style="display:none;"></div>
        <button class="id-folks-swap-btn"></button>
      </div>
    </div>`;
}
function mountPanel(holdings) {
  document.body.innerHTML = panelHTML(holdings);
  return document.querySelector(".id-folks-panel");
}
function optionEl(id, unit, decimals) {
  const li = document.createElement("li");
  li.className = "id-folks-asset-option";
  li.dataset.id = String(id);
  li.dataset.unit = unit;
  li.dataset.decimals = String(decimals);
  return li;
}

describe("pure helpers", () => {
  test("folksConfig reads router config", () => {
    const root = document.createElement("div");
    root.dataset.network = "testnet";
    root.dataset.referrer = "REF";
    root.dataset.feeBps = "25";
    expect(F.folksConfig(root)).toEqual({ network: "testnet", referrer: "REF", feeBps: 25 });
  });
  test("folksConfig defaults", () => {
    expect(F.folksConfig(document.createElement("div"))).toEqual({
      network: "mainnet", referrer: "", feeBps: 0,
    });
  });
  test("readPanelHoldings parses the island", () => {
    const panel = mountPanel([{ id: 0, unit: "ALGO", decimals: 6, amount: 5 }]);
    expect(F.readPanelHoldings(panel)).toEqual([{ id: 0, unit: "ALGO", decimals: 6, amount: 5 }]);
  });
  test("readPanelHoldings returns [] on bad JSON", () => {
    document.body.innerHTML = '<div class="id-folks-panel"><script class="id-folks-holdings">{bad</script></div>';
    expect(F.readPanelHoldings(document.querySelector(".id-folks-panel"))).toEqual([]);
  });
  test("isOptedIn", () => {
    const h = [{ id: 0 }, { id: 31566704 }];
    expect(F.isOptedIn(h, 31566704)).toBe(true);
    expect(F.isOptedIn(h, "0")).toBe(true);
    expect(F.isOptedIn(h, 999)).toBe(false);
  });
  test("decimalToBaseUnits / baseUnitsToDecimal round-trip + truncation", () => {
    expect(F.decimalToBaseUnits("1.5", 6)).toBe(BigInt(1500000));
    expect(F.decimalToBaseUnits("0.1234567", 6)).toBe(BigInt(123456)); // extra dp truncated
    expect(F.baseUnitsToDecimal(BigInt(1500000), 6)).toBe("1.5");
    expect(F.baseUnitsToDecimal(BigInt(2000000), 6)).toBe("2");
  });
  test("b64ToBytes decodes", () => {
    expect(Array.from(F.b64ToBytes(btoa("ABC")))).toEqual([65, 66, 67]);
  });
});

describe("readQuoteParams", () => {
  test("returns null until from/to/amount complete", () => {
    const panel = mountPanel([]);
    expect(F.readQuoteParams(panel, "ADDR")).toBeNull();
  });
  test("returns params when complete", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    const to = panel.querySelector(".id-folks-to");
    to.value = "31566704";
    panel.querySelector(".id-folks-amount").value = "2.5";
    const p = F.readQuoteParams(panel, "ADDR");
    expect(p).toEqual({
      fromAssetId: 0, toAssetId: 31566704, amount: BigInt(2500000),
      slippagePct: 0.5, fromAddress: "ADDR",
    });
  });
  test("returns null for zero amount", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "5";
    panel.querySelector(".id-folks-amount").value = "0";
    expect(F.readQuoteParams(panel, "ADDR")).toBeNull();
  });
});

describe("selectTarget", () => {
  test("opted-in target hides the notice and sets the hidden input", () => {
    const panel = mountPanel([{ id: 31566704, unit: "USDC", decimals: 6, amount: 0 }]);
    const ctx = { quoteTimer: null };
    F.selectTarget(panel, optionEl(31566704, "USDC", 6), ctx);
    const to = panel.querySelector(".id-folks-to");
    expect(to.value).toBe("31566704");
    expect(to.dataset.optedIn).toBe("1");
    expect(panel.querySelector(".id-folks-optin-notice").style.display).toBe("none");
  });
  test("non-opted-in target shows the opt-in notice", () => {
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(async () => { order.push("optIn"); return "OPTTX"; }),
      signAndSend: jest.fn(async () => { order.push("sign"); return "TXID"; }),
    };
    const panel = mountPanel([{ id: 0, unit: "ALGO", decimals: 6, amount: 5 }]);
    F.selectTarget(panel, optionEl(999, "NEW", 2), { quoteTimer: null });
    const to = panel.querySelector(".id-folks-to");
    expect(to.dataset.optedIn).toBe("0");
    expect(panel.querySelector(".id-folks-optin-notice").style.display).toBe("block");
  });
});

describe("fetchHoldings", () => {
  afterEach(() => { delete global.fetch; });
  test("extracts the holdings island from returned HTML", async () => {
    const holdings = [{ id: 0, amount: 9 }];
    global.fetch = jest.fn(async () => ({ text: async () => panelHTML(holdings) }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual(holdings);
    expect(global.fetch).toHaveBeenCalledWith("/u", { headers: { "HX-Request": "true" } });
  });
  test("returns [] when no island present", async () => {
    global.fetch = jest.fn(async () => ({ text: async () => "<div></div>" }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });
});

describe("refreshQuote", () => {
  afterEach(() => { delete window.asastatsSwap; });
  test("fetches a quote, renders it, enables the button when owned", async () => {

    const panel = mountPanel([]);
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-to").dataset.decimals = "6";
    panel.querySelector(".id-folks-amount").value = "1";
    const quote = {
      amountOut: BigInt(2000000), minimumReceived: BigInt(1990000),
      priceImpactPct: 0.1, routeLabel: "Folks Router", feesTotal: 2000
    };
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn(async () => quote) }, quoteTimer: null
    };
    await F.refreshQuote(panel, ctx);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
    expect(ctx.lastQuote).toBe(quote);
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(false);
    expect(panel.querySelector(".id-folks-quote").textContent).toContain("Folks Router");
  });
  test("disables the button and does not quote when params incomplete", async () => {
    const panel = mountPanel([]);
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn() }, quoteTimer: null
    };
    await F.refreshQuote(panel, ctx);
    expect(ctx.adapter.getQuote).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(true);
  });
});

describe("executeSwap", () => {
  afterEach(() => { delete global.fetch; delete window.asastatsSwap; });
  function ready(panel) {
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-amount").value = "1";
  }
  test("opted-in target: no opt-in, builds and signs", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([{ id: 0, amount: 5000000 }, { id: 31566704, amount: 0 }])
    }));
    window.asastatsSwap = { activeAddress: () => "ADDR", optIn: jest.fn(), signAndSend: jest.fn(async () => "TXID") };
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => [new Uint8Array([1])]) }
    };
    await F.executeSwap(panel, ctx);
    expect(window.asastatsSwap.optIn).not.toHaveBeenCalled();
    expect(ctx.adapter.buildSwapGroup).toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-status").textContent).toContain("TXID");
    const link = panel.querySelector(".id-folks-tx-link");
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("https://allo.info/tx/TXID");
    expect(panel.querySelector(".id-folks-amount").value).toBe("");
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(true);
  });
  test("non-opted-in target: pre-flight opt-in before signing", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([{ id: 0, amount: 5000000 }])
    }));  // target 31566704 absent => not opted in
    const order = [];
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(async () => { order.push("optIn"); return "OPTTX"; }),
      signAndSend: jest.fn(async () => { order.push("sign"); return "TXID"; }),
    };
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => { order.push("build"); return []; }) }
    };
    await F.executeSwap(panel, ctx);
    expect(window.asastatsSwap.optIn).toHaveBeenCalledWith(31566704);
    expect(order).toEqual(["optIn", "build", "sign"]);
  });
  test("insufficient balance aborts before building", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([{ id: 0, amount: 100 }])
    }));  // less than 1 ALGO
    window.asastatsSwap = { activeAddress: () => "ADDR", optIn: jest.fn(), signAndSend: jest.fn() };
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} }, adapter: { buildSwapGroup: jest.fn() }
    };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-status").textContent).toContain("Insufficient");
  });
});

describe("FolksAdapter", () => {
  beforeEach(() => {
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {}
    window.FolksRouter = {
      Network: { MAINNET: "MAIN", TESTNET: "TEST" },
      SwapMode: { FIXED_INPUT: "FI" },
      FolksRouterClient: jest.fn(function (network) {
        this.network = network;
        this.fetchSwapQuote = jest.fn(async () => ({
          quoteAmount: BigInt(2000000), priceImpact: 0.1, microalgoTxnsFee: 2000,
        }));
        this.prepareSwapTransactions = jest.fn(async () => [btoa("AB"), btoa("CD")]);
        this.fetchUserDiscount = jest.fn(async () => 10);
      }),
    };
  });
  afterEach(() => { delete window.FolksRouter; F.FolksAdapter._clients = {}; F.FolksAdapter._discounts = {}; });

  test("getQuote passes fee+referrer and computes minimumReceived", async () => {
    const q = await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1000000), slippagePct: 0.5 },
      { network: "mainnet", referrer: "REF", feeBps: 25 }
    );
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(q.minimumReceived).toBe(BigInt(1990000)); // 0.5% slippage = 50 bps
    expect(q.routeLabel).toBe("Folks Router");
    const client = F.FolksAdapter._clients.mainnet;
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.objectContaining({ fromAssetId: 0, toAssetId: 5, swapMode: "FI" }),
      undefined, undefined, undefined, "REF"
    );
  });
  test("getQuote on testnet builds a testnet client", async () => {
    await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1), slippagePct: 0 },
      { network: "testnet", referrer: "", feeBps: 0 }
    );
    expect(window.FolksRouter.FolksRouterClient).toHaveBeenCalledWith("TEST");
  });
  test("buildSwapGroup decodes the prepared base64 group to bytes", async () => {
    const group = await F.FolksAdapter.buildSwapGroup(
      { raw: { params: {}, slippageBps: 50, swapQuote: {} } }, "ADDR",
      { network: "mainnet" }
    );
    expect(group).toHaveLength(2);
    expect(Array.from(group[0])).toEqual([65, 66]); // "AB"
  });
});

describe("error branches", () => {
  afterEach(() => { delete global.fetch; delete window.asastatsSwap; });
  test("readPanelHoldings returns [] when island absent", () => {
    document.body.innerHTML = '<div class="id-folks-panel"></div>';
    expect(F.readPanelHoldings(document.querySelector(".id-folks-panel"))).toEqual([]);
  });
  test("refreshQuote surfaces a quote error and disables the button", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "5";
    panel.querySelector(".id-folks-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn(async () => { throw new Error("no route"); }) },
      quoteTimer: null
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-folks-status").textContent).toContain("no route");
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(true);
  });
  test("executeSwap surfaces a signing failure", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-amount").value = "1";
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([{ id: 0, amount: 5000000 }, { id: 31566704, amount: 0 }])
    }));
    window.asastatsSwap = { activeAddress: () => "ADDR", optIn: jest.fn(),
      signAndSend: jest.fn(async () => { throw new Error("user rejected"); }) };    
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} }, adapter: { buildSwapGroup: jest.fn(async () => []) }
    };
    await F.executeSwap(panel, ctx);
    expect(panel.querySelector(".id-folks-status").textContent).toContain("user rejected");
  });
  test("executeSwap no-ops without a quote", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "5";
    panel.querySelector(".id-folks-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: null, adapter: { buildSwapGroup: jest.fn() }
    };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
  });
  test("renderQuote no-ops without an output element; setPanelStatus tolerates missing el", () => {
    const bare = document.createElement("div");
    expect(() => F.renderQuote(bare, {
      amountOut: BigInt(1), minimumReceived: BigInt(1),
      priceImpactPct: 0, routeLabel: "x", feesTotal: 0
    })).not.toThrow();
    expect(() => F.setPanelStatus(bare, "hi")).not.toThrow();
  });
});

describe("debounce + fetch edge", () => {
  afterEach(() => { delete global.fetch; jest.useRealTimers(); });
  test("scheduleQuote debounces into refreshQuote when the timer fires", () => {
    jest.useFakeTimers();
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "5";
    panel.querySelector(".id-folks-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR", owns: true, cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          amountOut: BigInt(1),
          minimumReceived: BigInt(1), priceImpactPct: 0, routeLabel: "r", feesTotal: 0
        }))
      },
      quoteTimer: null
    };
    F.scheduleQuote(panel, ctx);
    expect(ctx.adapter.getQuote).not.toHaveBeenCalled();
    jest.advanceTimersByTime(400);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
  });
  test("fetchHoldings returns [] when the island holds bad JSON", async () => {
    global.fetch = jest.fn(async () => ({
      text: async () =>
        '<script class="id-folks-holdings">{bad</script>'
    }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });
});

describe("applyImpliedSource", () => {
  function panelWith(ids) {
    document.body.innerHTML =
      '<div class="id-folks-panel"><select class="id-folks-from">' +
      ids.map((i) => `<option value="${i}">u</option>`).join("") +
      "</select></div>";
    return document.querySelector(".id-folks-panel");
  }

  test("selects the source option when the asset is held", () => {
    const panel = panelWith(["0", "31566704"]);
    expect(F.applyImpliedSource(panel, "31566704")).toBe(true);
    expect(panel.querySelector(".id-folks-from").value).toBe("31566704");
  });

  test("is a no-op when the asset is not in the from-options", () => {
    const panel = panelWith(["0"]);
    expect(F.applyImpliedSource(panel, "31566704")).toBe(false);
  });

  test("is a no-op when no source is provided", () => {
    const panel = panelWith(["0"]);
    expect(F.applyImpliedSource(panel, null)).toBe(false);
  });

  test("is a no-op when the panel has no from-select", () => {
    document.body.innerHTML = '<div class="id-folks-panel"></div>';
    const panel = document.querySelector(".id-folks-panel");
    expect(F.applyImpliedSource(panel, "1")).toBe(false);
  });
});

describe("branch coverage", () => {
  function panel(html) {
    document.body.innerHTML = '<div class="id-folks-panel">' + html + "</div>";
    return document.querySelector(".id-folks-panel");
  }
  afterEach(() => { F.FolksAdapter._clients = {}; });

  test("_clientFor: testnet network + client caching", () => {
    delete F.FolksAdapter._clients;
    const ClientCtor = jest.fn(function (net) { this.net = net; });
    window.FolksRouter = {
      FolksRouterClient: ClientCtor,
      Network: { MAINNET: "mainnet", TESTNET: "testnet" },
    };
    const a = F.FolksAdapter._clientFor({ network: "testnet" });
    const b = F.FolksAdapter._clientFor({ network: "testnet" });
    expect(a).toBe(b);
    expect(ClientCtor).toHaveBeenCalledTimes(1);
    expect(ClientCtor).toHaveBeenCalledWith("testnet");
  });

  test("readPanelHoldings: empty island -> []", () => {
    expect(F.readPanelHoldings(panel('<script class="id-folks-holdings"></script>'))).toEqual([]);
  });

  test("fetchHoldings: empty island -> []", async () => {
    global.fetch = jest.fn(async () => ({ text: async () => '<script class="id-folks-holdings"></script>' }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });

  test("selectTarget: missing decimals/unit defaults, no results node", () => {
    const p = panel('<input class="id-folks-to" type="hidden">' +
      '<span class="id-folks-optin-notice"></span><input class="id-folks-to-search">');
    const opt = document.createElement("div"); opt.dataset.id = "31566704";
    F.selectTarget(p, opt, { quoteTimer: null });
    expect(p.querySelector(".id-folks-to").dataset.decimals).toBe("0");
    expect(p.querySelector(".id-folks-to").dataset.unit).toBe("");
    expect(p.querySelector(".id-folks-to-search").value).toBe("ASA (#31566704)");
  });

  test("readQuoteParams: default decimals + empty slippage", () => {
    const p = panel('<select class="id-folks-from"><option value="0" data-amount="5000000">A</option></select>' +
      '<input class="id-folks-to" value="31566704"><input class="id-folks-amount" value="1">' +
      '<input class="id-folks-slippage" value="">');
    expect(F.readQuoteParams(p, "ADDR").slippagePct).toBe(0.5);
  });

  test("refreshQuote: incomplete form, no button", async () => {
    const p = panel('<select class="id-folks-from"></select><input class="id-folks-to" value="">' +
      '<input class="id-folks-amount" value=""><input class="id-folks-slippage" value="0.5">');
    await F.refreshQuote(p, { owns: true });
  });

  test("refreshQuote: success, no button", async () => {
    const p = panel('<select class="id-folks-from"><option value="0" data-decimals="6">A</option></select>' +
      '<input class="id-folks-to" value="31566704"><input class="id-folks-amount" value="1">' +
      '<input class="id-folks-slippage" value="0.5"><div class="id-folks-status"></div>');
    const adapter = { getQuote: jest.fn().mockResolvedValue({ amountOut: 1n, minimumReceived: 1n, priceImpactPct: 0, feesTotal: 0, routeLabel: "X" }) };
    await F.refreshQuote(p, { adapter, cfg: {}, owns: true });
    expect(adapter.getQuote).toHaveBeenCalled();
  });

  test("refreshQuote: error, no button", async () => {
    const p = panel('<select class="id-folks-from"><option value="0" data-decimals="6">A</option></select>' +
      '<input class="id-folks-to" value="31566704"><input class="id-folks-amount" value="1">' +
      '<input class="id-folks-slippage" value="0.5"><div class="id-folks-status"></div>');
    await F.refreshQuote(p, { adapter: { getQuote: jest.fn().mockRejectedValue(new Error("boom")) }, cfg: {}, owns: true });
    expect(p.querySelector(".id-folks-status").textContent).toContain("boom");
  });

  test("executeSwap: no button, insufficient balance hits finally", async () => {
    global.fetch = jest.fn(async () => ({ text: async () => '<script class="id-folks-holdings">[{"id":0,"amount":"1"}]</script>' }));
    const p = panel('<select class="id-folks-from"><option value="0" data-decimals="6">A</option></select>' +
      '<input class="id-folks-to" value="31566704"><input class="id-folks-amount" value="1">' +
      '<input class="id-folks-slippage" value="0.5"><div class="id-folks-status"></div>');
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    await F.executeSwap(p, { adapter: {}, cfg: {}, fromAddress: "ADDR", owns: true, lastQuote: {}, holdingsUrl: "/u" });
    expect(p.querySelector(".id-folks-status").textContent).toContain("Insufficient");
    delete window.asastatsSwap;
  });

  test("decimalToBaseUnits: leading dot + zero decimals", () => {
    expect(F.decimalToBaseUnits(".5", 6)).toBe(500000n);
    expect(F.decimalToBaseUnits("5", 0)).toBe(5n);
  });
});

describe("inline reveal helpers", () => {
  test("readPanelCfg: reads the cfg island", () => {
    document.body.innerHTML =
      '<div class="id-folks-panel"><span class="id-folks-cfg" data-router="folks"' +
      ' data-network="testnet" data-referrer="REF" data-fee-bps="25"></span></div>';
    const cfg = F.readPanelCfg(document.querySelector(".id-folks-panel"));
    expect(cfg).toEqual({ router: "folks", network: "testnet", referrer: "REF", feeBps: 25 });
  });
  test("readPanelCfg: defaults when attrs missing", () => {
    document.body.innerHTML = '<div class="id-folks-panel"><span class="id-folks-cfg"></span></div>';
    expect(F.readPanelCfg(document.querySelector(".id-folks-panel"))).toEqual({
      router: "", network: "mainnet", referrer: "", feeBps: 0
    });
  });
  test("readPanelCfg: null when no island", () => {
    document.body.innerHTML = '<div class="id-folks-panel"></div>';
    expect(F.readPanelCfg(document.querySelector(".id-folks-panel"))).toBeNull();
  });

  test("inlineHoldingsUrl: fills address + from", () => {
    expect(F.inlineHoldingsUrl("/widgets/folks/ADDRESS/holdings", "AAAA", "31566704"))
      .toBe("/widgets/folks/AAAA/holdings?from=31566704");
  });
  test("inlineHoldingsUrl: omits from when absent", () => {
    expect(F.inlineHoldingsUrl("/widgets/folks/ADDRESS/holdings", "AAAA", null))
      .toBe("/widgets/folks/AAAA/holdings");
  });
  test("inlineHoldingsUrl: empty without tmpl or address", () => {
    expect(F.inlineHoldingsUrl("", "AAAA", "1")).toBe("");
    expect(F.inlineHoldingsUrl("/x/ADDRESS", "", "1")).toBe("");
  });
});

// ---- modal swap helpers (markerCfg / applyPercent / percentage row / mode) ----
describe("modal swap helpers", () => {
  function makePanel(opts) {
    opts = opts || {};
    const wrap = document.createElement("div");
    wrap.className = "id-folks-form";
    const sel = document.createElement("select");
    sel.className = "id-folks-from";
    if (opts.withOption !== false) {
      const o = document.createElement("option");
      o.value = "31566704";
      o.dataset.decimals = String(opts.decimals != null ? opts.decimals : 6);
      if (opts.amount !== null) o.dataset.amount = opts.amount || "1000000000";
      o.textContent = "USDC";
      sel.appendChild(o);
    }
    wrap.appendChild(sel);
    const amount = document.createElement("input");
    amount.className = "id-folks-amount";
    wrap.appendChild(amount);
    return wrap;
  }

  test("markerCfg: null -> null", () => {
    expect(F.markerCfg(null)).toBeNull();
  });
  test("markerCfg: defaults when only router set", () => {
    const m = document.createElement("span");
    m.dataset.router = "folks";
    expect(F.markerCfg(m)).toEqual({ router: "folks", network: "mainnet", referrer: "", feeBps: 0 });
  });
  test("markerCfg: explicit network/referrer/feeBps", () => {
    const m = document.createElement("span");
    m.dataset.router = "folks";
    m.dataset.network = "testnet";
    m.dataset.referrer = "ADDR";
    m.dataset.feeBps = "30";
    expect(F.markerCfg(m)).toEqual({ router: "folks", network: "testnet", referrer: "ADDR", feeBps: 30 });
  });

  test("applyPercent: 50/25/100 of 1000.0 @ 6dp", () => {
    expect(F.applyPercent("1000000000", 6, 50)).toBe("500");
    expect(F.applyPercent("1000000000", 6, 25)).toBe("250");
    expect(F.applyPercent("1000000000", 6, 100)).toBe("1000");
  });
  test("applyPercent: fractional percent keeps precision", () => {
    expect(F.applyPercent("1000000000", 6, 33.33)).toBe("333.3");
  });
  test("applyPercent: clamps range and NaN", () => {
    expect(F.applyPercent("1000000000", 6, 150)).toBe("1000");
    expect(F.applyPercent("1000000000", 6, -5)).toBe("0");
    expect(F.applyPercent("1000000000", 6, "abc")).toBe("0");
  });

  test("sourceHoldingsBaseUnits: selected amount as bigint", () => {
    expect(F.sourceHoldingsBaseUnits(makePanel())).toBe(BigInt("1000000000"));
  });
  test("sourceHoldingsBaseUnits: null without select", () => {
    expect(F.sourceHoldingsBaseUnits(document.createElement("div"))).toBeNull();
  });
  test("sourceHoldingsBaseUnits: null with no value", () => {
    expect(F.sourceHoldingsBaseUnits(makePanel({ withOption: false }))).toBeNull();
  });
  test("sourceHoldingsBaseUnits: null when option lacks data-amount", () => {
    expect(F.sourceHoldingsBaseUnits(makePanel({ amount: null }))).toBeNull();
  });

  test("setAmountFromPercent: writes field, returns value", () => {
    const p = makePanel();
    expect(F.setAmountFromPercent(p, 75)).toBe("750");
    expect(p.querySelector(".id-folks-amount").value).toBe("750");
  });
  test("setAmountFromPercent: '' when holdings unresolved", () => {
    expect(F.setAmountFromPercent(makePanel({ amount: null }), 50)).toBe("");
  });
  test("setAmountFromPercent: '' when amount field missing", () => {
    const p = makePanel();
    p.querySelector(".id-folks-amount").remove();
    expect(F.setAmountFromPercent(p, 50)).toBe("");
  });

  test("applySwapMode: null form -> 'sell'", () => {
    expect(F.applySwapMode(null, "buy")).toBe("sell");
  });
  test("applySwapMode: buy adds class, sell removes it", () => {
    const f = document.createElement("div");
    expect(F.applySwapMode(f, "buy")).toBe("buy");
    expect(f.classList.contains("folks-mode-buy")).toBe(true);
    expect(F.applySwapMode(f, "sell")).toBe("sell");
    expect(f.classList.contains("folks-mode-buy")).toBe(false);
  });
});

describe("modal swap helpers — defensive branches", () => {
  test("markerCfg: router defaults to '' when absent", () => {
    const m = document.createElement("span"); // no data-router
    expect(F.markerCfg(m).router).toBe("");
  });
  test("sourceHoldingsBaseUnits: empty data-amount -> 0n", () => {
    const wrap = document.createElement("div");
    const sel = document.createElement("select");
    sel.className = "id-folks-from";
    const o = document.createElement("option");
    o.value = "1";
    o.dataset.amount = ""; // defined but empty -> hits `|| "0"`
    sel.appendChild(o);
    wrap.appendChild(sel);
    expect(F.sourceHoldingsBaseUnits(wrap)).toBe(BigInt(0));
  });
  test("setAmountFromPercent: missing decimals -> treated as 0dp", () => {
    const wrap = document.createElement("div");
    const sel = document.createElement("select");
    sel.className = "id-folks-from";
    const o = document.createElement("option");
    o.value = "1";
    o.dataset.amount = "250"; // no data-decimals -> `|| "0"`
    sel.appendChild(o);
    wrap.appendChild(sel);
    const amount = document.createElement("input");
    amount.className = "id-folks-amount";
    wrap.appendChild(amount);
    expect(F.setAmountFromPercent(wrap, 50)).toBe("125"); // 0dp
  });
});

describe("toggleInlineSwap — additional cases", () => {
  const labels = { show: "Swap", hide: "Hide" };

  test("round-trips both label directions with a label present", () => {
    document.body.innerHTML =
      '<div id="w"></div><a><span class="swap-label">Hide</span></a>';
    const wrap = document.getElementById("w");
    const label = document.querySelector(".swap-label");

    // visible -> hidden: nowHidden === true -> labels.show
    expect(F.toggleInlineSwap(wrap, label, labels)).toBe(false);
    expect(wrap.classList.contains("hidden")).toBe(true);
    expect(label.textContent).toBe("Swap");

    // hidden -> visible: nowHidden === false -> labels.hide
    expect(F.toggleInlineSwap(wrap, label, labels)).toBe(true);
    expect(wrap.classList.contains("hidden")).toBe(false);
    expect(label.textContent).toBe("Hide");
  });

  test("tolerates a missing label element on the hide direction", () => {
    document.body.innerHTML = '<div id="w"></div>'; // starts visible
    const wrap = document.getElementById("w");
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(false);
    expect(wrap.classList.contains("hidden")).toBe(true);
  });

  test("round-trips deterministically across repeated toggles", () => {
    document.body.innerHTML = '<div id="w" class="hidden"></div>';
    const wrap = document.getElementById("w");
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(true);  // reveal
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(false); // hide
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(true);  // reveal
    expect(wrap.classList.contains("hidden")).toBe(false);
  });

  test("returns a strict boolean", () => {
    document.body.innerHTML = '<div id="w" class="hidden"></div>';
    expect(typeof F.toggleInlineSwap(document.getElementById("w"), null, labels))
      .toBe("boolean");
  });
});
describe("swap success + dirty helpers", () => {
  test("alloTxUrl builds the explorer URL (and encodes)", () => {
    expect(F.alloTxUrl("ABC123")).toBe("https://allo.info/tx/ABC123");
    expect(F.alloTxUrl("a/b c")).toBe("https://allo.info/tx/a%2Fb%20c");
  });

  function panelWith() {
    const p = document.createElement("div");
    p.innerHTML =
      '<div class="id-folks-status"></div>' +
      '<input class="id-folks-amount" value="1.5">' +
      '<input class="id-folks-pct" value="50">' +
      '<div class="id-folks-quote">≈ 100</div>';
    return p;
  }

  test("renderSwapSuccess: builds link and resets amount/pct/quote", () => {
    const p = panelWith();
    F.renderSwapSuccess(p, "TXID");
    const link = p.querySelector(".id-folks-tx-link");
    expect(link.getAttribute("href")).toBe("https://allo.info/tx/TXID");
    expect(link.textContent).toBe("TXID");
    expect(link.target).toBe("_blank");
    expect(p.querySelector(".id-folks-status").textContent).toBe("Swap submitted: TXID");
    expect(p.querySelector(".id-folks-amount").value).toBe("");
    expect(p.querySelector(".id-folks-pct").value).toBe("");
    expect(p.querySelector(".id-folks-quote").textContent).toBe("");
  });

  test("renderSwapSuccess: tolerates missing optional elements", () => {
    const bare = document.createElement("div"); // no status/amount/pct/quote
    expect(() => F.renderSwapSuccess(bare, "TXID")).not.toThrow();
  });

  test("markSwapDirty: sets folksDirty on the enclosing modal", () => {
    const modal = document.createElement("div");
    modal.className = "modal";
    const panel = document.createElement("div");
    modal.appendChild(panel);
    expect(F.markSwapDirty(panel)).toBe(true);
    expect(modal.dataset.folksDirty).toBe("1");
  });

  test("markSwapDirty: no-op when not inside a modal", () => {
    expect(F.markSwapDirty(document.createElement("div"))).toBe(false);
  });
});

describe("getQuote discount handling", () => {
  function clientMock(discountImpl) {
    const client = {
      fetchSwapQuote: jest.fn(async () => ({
        quoteAmount: BigInt(2000000), priceImpact: 0.1, microalgoTxnsFee: 2000,
      })),
      fetchUserDiscount: discountImpl || jest.fn(async () => 10),
      prepareSwapTransactions: jest.fn(),
    };
    window.FolksRouter = {
      Network: { MAINNET: "MAIN", TESTNET: "TEST" },
      SwapMode: { FIXED_INPUT: "FI" },
      FolksRouterClient: jest.fn(() => client),
    };
    return client;
  }
  beforeEach(() => { F.FolksAdapter._clients = {}; F.FolksAdapter._discounts = {}; });
  afterEach(() => { delete window.FolksRouter; F.FolksAdapter._clients = {}; F.FolksAdapter._discounts = {}; });

  test("fetches the user discount and passes it (no feeBps)", async () => {
    const client = clientMock();
    await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1), slippagePct: 0, fromAddress: "USER" },
      { network: "mainnet", referrer: "REF" }
    );
    expect(client.fetchUserDiscount).toHaveBeenCalledWith("USER");
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.objectContaining({ fromAssetId: 0, toAssetId: 5 }),
      undefined, undefined, 10, "REF"
    );
  });
  test("caches the discount per address (one lookup across quotes)", async () => {
    delete F.FolksAdapter._discounts; // exercise lazy-init
    const client = clientMock();
    const p = { fromAssetId: 0, toAssetId: 5, amount: BigInt(1), slippagePct: 0, fromAddress: "USER" };
    await F.FolksAdapter.getQuote(p, { network: "mainnet" });
    await F.FolksAdapter.getQuote(p, { network: "mainnet" });
    expect(client.fetchUserDiscount).toHaveBeenCalledTimes(1);
  });
  test("a discount lookup failure does not block the quote", async () => {
    const client = clientMock(jest.fn(async () => { throw new Error("down"); }));
    const q = await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1), slippagePct: 0, fromAddress: "USER" },
      { network: "mainnet" }
    );
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.anything(), undefined, undefined, undefined, undefined
    );
  });
});

describe("walletOwns + applyOwnership", () => {
  afterEach(() => { delete window.asastatsSwap; });
  test("walletOwns: false without a bridge", () => {
    expect(F.walletOwns("ADDR")).toBe(false);
  });
  test("walletOwns: false for a falsy address", () => {
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    expect(F.walletOwns("")).toBe(false);
  });
  test("walletOwns: false when the active account differs", () => {
    window.asastatsSwap = { activeAddress: () => "OTHER" };
    expect(F.walletOwns("ADDR")).toBe(false);
  });
  test("walletOwns: true when the active account matches", () => {
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    expect(F.walletOwns("ADDR")).toBe(true);
  });

  function ownPanel() {
    const p = document.createElement("div");
    p.innerHTML =
      '<button class="id-folks-swap-btn" disabled></button>' +
      '<div class="id-folks-connect-notice" style="display:none;"></div>';
    return p;
  }
  test("applyOwnership(true): enables button, hides notice", () => {
    const p = ownPanel();
    expect(F.applyOwnership(p, true)).toBe(true);
    expect(p.querySelector(".id-folks-swap-btn").disabled).toBe(false);
    expect(p.querySelector(".id-folks-connect-notice").style.display).toBe("none");
  });
  test("applyOwnership(false): disables button, shows notice", () => {
    const p = ownPanel();
    F.applyOwnership(p, false);
    expect(p.querySelector(".id-folks-swap-btn").disabled).toBe(true);
    expect(p.querySelector(".id-folks-connect-notice").style.display).toBe("block");
  });
  test("applyOwnership tolerates missing button/notice", () => {
    expect(() => F.applyOwnership(document.createElement("div"), true)).not.toThrow();
  });
});

describe("executeSwap ownership gate", () => {
  afterEach(() => { delete global.fetch; delete window.asastatsSwap; });
  test("does not build/sign when the wallet is not the from-address", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-amount").value = "1";
    window.asastatsSwap = { activeAddress: () => "OTHER", optIn: jest.fn(), signAndSend: jest.fn() };
    global.fetch = jest.fn();
    const ctx = { fromAddress: "ADDR", owns: false, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} }, adapter: { buildSwapGroup: jest.fn() } };
    await F.executeSwap(panel, ctx);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-status").textContent).toContain("Connect the wallet");
  });
});

describe("inlineHoldingsUrl encoding", () => {
  test("encodes the from-asset query value", () => {
    expect(F.inlineHoldingsUrl("/w/ADDRESS/h", "ADDR", "a b&c")).toBe("/w/ADDR/h?from=a%20b%26c");
  });
  test("numeric from-asset is unchanged", () => {
    expect(F.inlineHoldingsUrl("/w/ADDRESS/h", "ADDR", "123")).toBe("/w/ADDR/h?from=123");
  });
});
