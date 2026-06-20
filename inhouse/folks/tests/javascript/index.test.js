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
  test("fetches a quote, renders it, enables the button when owned", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-to").dataset.decimals = "6";
    panel.querySelector(".id-folks-amount").value = "1";
    const quote = { amountOut: BigInt(2000000), minimumReceived: BigInt(1990000),
      priceImpactPct: 0.1, routeLabel: "Folks Router", feesTotal: 2000 };
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn(async () => quote) }, quoteTimer: null };
    await F.refreshQuote(panel, ctx);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
    expect(ctx.lastQuote).toBe(quote);
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(false);
    expect(panel.querySelector(".id-folks-quote").textContent).toContain("Folks Router");
  });
  test("disables the button and does not quote when params incomplete", async () => {
    const panel = mountPanel([]);
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn() }, quoteTimer: null };
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
    global.fetch = jest.fn(async () => ({ text: async () =>
      panelHTML([{ id: 0, amount: 5000000 }, { id: 31566704, amount: 0 }]) }));
    window.asastatsSwap = { optIn: jest.fn(), signAndSend: jest.fn(async () => "TXID") };
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => [new Uint8Array([1])]) } };
    await F.executeSwap(panel, ctx);
    expect(window.asastatsSwap.optIn).not.toHaveBeenCalled();
    expect(ctx.adapter.buildSwapGroup).toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-status").textContent).toContain("TXID");
  });
  test("non-opted-in target: pre-flight opt-in before signing", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({ text: async () =>
      panelHTML([{ id: 0, amount: 5000000 }]) }));  // target 31566704 absent => not opted in
    const order = [];
    window.asastatsSwap = {
      optIn: jest.fn(async () => { order.push("optIn"); return "OPTTX"; }),
      signAndSend: jest.fn(async () => { order.push("sign"); return "TXID"; }),
    };
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => { order.push("build"); return []; }) } };
    await F.executeSwap(panel, ctx);
    expect(window.asastatsSwap.optIn).toHaveBeenCalledWith(31566704);
    expect(order).toEqual(["optIn", "build", "sign"]);
  });
  test("insufficient balance aborts before building", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({ text: async () =>
      panelHTML([{ id: 0, amount: 100 }]) }));  // less than 1 ALGO
    window.asastatsSwap = { optIn: jest.fn(), signAndSend: jest.fn() };
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} }, adapter: { buildSwapGroup: jest.fn() } };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-folks-status").textContent).toContain("Insufficient");
  });
});

describe("FolksAdapter", () => {
  beforeEach(() => {
    F.FolksAdapter._client = null;
    window.FolksRouter = {
      Network: { MAINNET: "MAIN", TESTNET: "TEST" },
      SwapMode: { FIXED_INPUT: "FI" },
      FolksRouterClient: jest.fn(function (network) {
        this.network = network;
        this.fetchSwapQuote = jest.fn(async () => ({
          quoteAmount: BigInt(2000000), priceImpact: 0.1, microalgoTxnsFee: 2000,
        }));
        this.prepareSwapTransactions = jest.fn(async () => [btoa("AB"), btoa("CD")]);
      }),
    };
  });
  afterEach(() => { delete window.FolksRouter; F.FolksAdapter._client = null; });

  test("getQuote passes fee+referrer and computes minimumReceived", async () => {
    const q = await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1000000), slippagePct: 0.5 },
      { network: "mainnet", referrer: "REF", feeBps: 25 }
    );
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(q.minimumReceived).toBe(BigInt(1990000)); // 0.5% slippage = 50 bps
    expect(q.routeLabel).toBe("Folks Router");
    const client = F.FolksAdapter._client;
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.objectContaining({ fromAssetId: 0, toAssetId: 5, swapMode: "FI" }),
      undefined, 25, undefined, "REF"
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
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn(async () => { throw new Error("no route"); }) },
      quoteTimer: null };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-folks-status").textContent).toContain("no route");
    expect(panel.querySelector(".id-folks-swap-btn").disabled).toBe(true);
  });
  test("executeSwap surfaces a signing failure", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "31566704";
    panel.querySelector(".id-folks-amount").value = "1";
    global.fetch = jest.fn(async () => ({ text: async () =>
      panelHTML([{ id: 0, amount: 5000000 }, { id: 31566704, amount: 0 }]) }));
    window.asastatsSwap = { optIn: jest.fn(),
      signAndSend: jest.fn(async () => { throw new Error("user rejected"); }) };
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: { raw: {} }, adapter: { buildSwapGroup: jest.fn(async () => []) } };
    await F.executeSwap(panel, ctx);
    expect(panel.querySelector(".id-folks-status").textContent).toContain("user rejected");
  });
  test("executeSwap no-ops without a quote", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-folks-from").value = "0";
    panel.querySelector(".id-folks-to").value = "5";
    panel.querySelector(".id-folks-amount").value = "1";
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {}, holdingsUrl: "/u",
      lastQuote: null, adapter: { buildSwapGroup: jest.fn() } };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
  });
  test("renderQuote no-ops without an output element; setPanelStatus tolerates missing el", () => {
    const bare = document.createElement("div");
    expect(() => F.renderQuote(bare, { amountOut: BigInt(1), minimumReceived: BigInt(1),
      priceImpactPct: 0, routeLabel: "x", feesTotal: 0 })).not.toThrow();
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
    const ctx = { fromAddress: "ADDR", owns: true, cfg: {},
      adapter: { getQuote: jest.fn(async () => ({ amountOut: BigInt(1),
        minimumReceived: BigInt(1), priceImpactPct: 0, routeLabel: "r", feesTotal: 0 })) },
      quoteTimer: null };
    F.scheduleQuote(panel, ctx);
    expect(ctx.adapter.getQuote).not.toHaveBeenCalled();
    jest.advanceTimersByTime(400);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
  });
  test("fetchHoldings returns [] when the island holds bad JSON", async () => {
    global.fetch = jest.fn(async () => ({ text: async () =>
      '<script class="id-folks-holdings">{bad</script>' }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });
});
