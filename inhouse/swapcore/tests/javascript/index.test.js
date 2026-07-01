const F = require("../../static/swap/swap.js");

function panelHTML(holdings) {
  return `
    <div class="id-swap-panel" data-holdings-url="/widgets/folks/A/holdings">
      <script type="application/json" class="id-swap-holdings">${JSON.stringify(holdings)}</script>
      <div class="id-swap-form" data-address="ADDR">
        <select class="id-swap-from">
          <option value="0" data-decimals="6" data-unit="ALGO" data-amount="5000000">ALGO</option>
        </select>
        <input class="id-swap-to-search">
        <div class="id-swap-to-results"></div>
        <input type="hidden" class="id-swap-to" data-decimals="" data-unit="" data-opted-in="">
        <input class="id-swap-amount">
        <input class="id-swap-slippage" value="0.5">
        <div class="id-swap-quote"></div>
        <div class="id-swap-status"></div>
        <div class="id-swap-optin-notice" style="display:none;"></div>
        <button class="id-swap-swap-btn"></button>
      </div>
    </div>`;
}
function mountPanel(holdings) {
  document.body.innerHTML = panelHTML(holdings);
  return document.querySelector(".id-swap-panel");
}
function optionEl(id, unit, decimals) {
  const li = document.createElement("li");
  li.className = "id-swap-asset-option";
  li.dataset.id = String(id);
  li.dataset.unit = unit;
  li.dataset.decimals = String(decimals);
  return li;
}

describe("pure helpers", () => {
  test("swapConfig reads router config", () => {
    const root = document.createElement("div");
    root.dataset.network = "testnet";
    root.dataset.referrer = "REF";
    root.dataset.feeBps = "25";
    expect(F.swapConfig(root)).toEqual({
      network: "testnet",
      referrer: "REF",
      feeBps: 25,
    });
  });
  test("swapConfig defaults", () => {
    expect(F.swapConfig(document.createElement("div"))).toEqual({
      network: "mainnet",
      referrer: "",
      feeBps: 0,
    });
  });
  test("readPanelHoldings parses the island", () => {
    const panel = mountPanel([{ id: 0, unit: "ALGO", decimals: 6, amount: 5 }]);
    expect(F.readPanelHoldings(panel)).toEqual([
      { id: 0, unit: "ALGO", decimals: 6, amount: 5 },
    ]);
  });
  test("readPanelHoldings returns [] on bad JSON", () => {
    document.body.innerHTML =
      '<div class="id-swap-panel"><script class="id-swap-holdings">{bad</script></div>';
    expect(
      F.readPanelHoldings(document.querySelector(".id-swap-panel")),
    ).toEqual([]);
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
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "31566704";
    panel.querySelector(".id-swap-amount").value = "2.5";
    const p = F.readQuoteParams(panel, "ADDR");
    expect(p).toEqual({
      mode: "sell",
      fromAssetId: 0,
      toAssetId: 31566704,
      amount: BigInt(2500000),
      slippagePct: 0.5,
      fromAddress: "ADDR",
    });
  });
  test("returns null for zero amount", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "5";
    panel.querySelector(".id-swap-amount").value = "0";
    expect(F.readQuoteParams(panel, "ADDR")).toBeNull();
  });
});

describe("selectTarget", () => {
  test("opted-in target hides the notice and sets the hidden input", () => {
    const panel = mountPanel([
      { id: 31566704, unit: "USDC", decimals: 6, amount: 0 },
    ]);
    const ctx = { quoteTimer: null };
    F.selectTarget(panel, optionEl(31566704, "USDC", 6), ctx);
    const to = panel.querySelector(".id-swap-to");
    expect(to.value).toBe("31566704");
    expect(to.dataset.optedIn).toBe("1");
    expect(panel.querySelector(".id-swap-optin-notice").style.display).toBe(
      "none",
    );
  });
  test("non-opted-in target shows the opt-in notice", () => {
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(async () => {
        order.push("optIn");
        return "OPTTX";
      }),
      signAndSend: jest.fn(async () => {
        order.push("sign");
        return "TXID";
      }),
    };
    const panel = mountPanel([{ id: 0, unit: "ALGO", decimals: 6, amount: 5 }]);
    F.selectTarget(panel, optionEl(999, "NEW", 2), { quoteTimer: null });
    const to = panel.querySelector(".id-swap-to");
    expect(to.dataset.optedIn).toBe("0");
    expect(panel.querySelector(".id-swap-optin-notice").style.display).toBe(
      "block",
    );
  });
});

describe("fetchHoldings", () => {
  afterEach(() => {
    delete global.fetch;
  });
  test("extracts the holdings island from returned HTML", async () => {
    const holdings = [{ id: 0, amount: 9 }];
    global.fetch = jest.fn(async () => ({
      text: async () => panelHTML(holdings),
    }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual(holdings);
    expect(global.fetch).toHaveBeenCalledWith("/u", {
      headers: { "HX-Request": "true" },
    });
  });
  test("returns [] when no island present", async () => {
    global.fetch = jest.fn(async () => ({ text: async () => "<div></div>" }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });
});

describe("refreshQuote", () => {
  afterEach(() => {
    delete window.asastatsSwap;
  });
  test("fetches a quote, renders it, enables the button when owned", async () => {
    const panel = mountPanel([]);
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "31566704";
    panel.querySelector(".id-swap-to").dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1";
    const quote = {
      amountOut: BigInt(2000000),
      minimumReceived: BigInt(1990000),
      priceImpactPct: 0.1,
      routeLabel: "Folks Router",
      feesTotal: 2000,
    };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      adapter: { getQuote: jest.fn(async () => quote) },
      quoteTimer: null,
    };
    await F.refreshQuote(panel, ctx);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
    expect(ctx.lastQuote).toBe(quote);
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(false);
    expect(panel.querySelector(".id-swap-quote").textContent).toContain(
      "Folks Router",
    );
  });
  test("disables the button and does not quote when params incomplete", async () => {
    const panel = mountPanel([]);
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      adapter: { getQuote: jest.fn() },
      quoteTimer: null,
    };
    await F.refreshQuote(panel, ctx);
    expect(ctx.adapter.getQuote).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(true);
  });
});

describe("executeSwap", () => {
  afterEach(() => {
    delete global.fetch;
    delete window.asastatsSwap;
  });
  function ready(panel) {
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "31566704";
    panel.querySelector(".id-swap-amount").value = "1";
  }
  test("opted-in target: no opt-in, builds and signs", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([
          { id: 0, amount: 5000000 },
          { id: 31566704, amount: 0 },
        ]),
    }));
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(),
      signAndSend: jest.fn(async () => "TXID"),
    };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => [new Uint8Array([1])]) },
    };
    await F.executeSwap(panel, ctx);
    expect(window.asastatsSwap.optIn).not.toHaveBeenCalled();
    expect(ctx.adapter.buildSwapGroup).toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).toHaveBeenCalled();
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "TXID",
    );
    const link = panel.querySelector(".id-swap-tx-link");
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("https://allo.info/tx/TXID");
    expect(panel.querySelector(".id-swap-amount").value).toBe("");
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(true);
  });
  test("non-opted-in target: passes userNeedsOptIn to signAndSend", async () => {
    const panel = mountPanel([]);
    ready(panel); // Assuming 'ready' sets the hidden target id to 31566704 and amount
    global.fetch = jest.fn(async () => ({
      text: async () => panelHTML([{ id: 0, amount: 5000000 }]),
    })); // target 31566704 absent => not opted in
    const order = [];
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      // Replaced optIn with just signAndSend since the bridge handles prepending
      signAndSend: jest.fn(async () => {
        order.push("sign");
        return "TXID";
      }),
    };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: {
        buildSwapGroup: jest.fn(async () => {
          order.push("build");
          return [];
        }),
      },
    };

    await F.executeSwap(panel, ctx);

    // Assert signAndSend is called with the userNeedsOptIn boolean set to true
    expect(window.asastatsSwap.signAndSend).toHaveBeenCalledWith(
      [], // the returned group array from buildSwapGroup mock
      {
        outputAssetId: 31566704,
        userNeedsOptIn: true,
        referrer: "",
      },
    );
    // The separate optIn call is gone, order is just build -> sign
    expect(order).toEqual(["build", "sign"]);
  });
  test("insufficient balance aborts before building", async () => {
    const panel = mountPanel([]);
    ready(panel);
    global.fetch = jest.fn(async () => ({
      text: async () => panelHTML([{ id: 0, amount: 100 }]),
    })); // less than 1 ALGO
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(),
      signAndSend: jest.fn(),
    };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn() },
    };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
    expect(window.asastatsSwap.signAndSend).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "Insufficient",
    );
  });
});

describe("FolksAdapter", () => {
  beforeEach(() => {
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
    window.FolksRouter = {
      Network: { MAINNET: "MAIN", TESTNET: "TEST" },
      SwapMode: { FIXED_INPUT: "FI" },
      FolksRouterClient: jest.fn(function (network) {
        this.network = network;
        this.fetchSwapQuote = jest.fn(async () => ({
          quoteAmount: BigInt(2000000),
          priceImpact: 0.1,
          microalgoTxnsFee: 2000,
        }));
        this.prepareSwapTransactions = jest.fn(async () => [
          btoa("AB"),
          btoa("CD"),
        ]);
        this.fetchUserDiscount = jest.fn(async () => 10);
      }),
    };
  });
  afterEach(() => {
    delete window.FolksRouter;
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
  });

  test("getQuote passes fee+referrer and computes minimumReceived", async () => {
    const q = await F.FolksAdapter.getQuote(
      {
        fromAssetId: 0,
        toAssetId: 5,
        amount: BigInt(1000000),
        slippagePct: 0.5,
      },
      { network: "mainnet", referrer: "REF", feeBps: 25 },
    );
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(q.minimumReceived).toBe(BigInt(1990000)); // 0.5% slippage = 50 bps
    expect(q.routeLabel).toBe("Folks Router");
    const client = F.FolksAdapter._clients.mainnet;
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.objectContaining({ fromAssetId: 0, toAssetId: 5, swapMode: "FI" }),
      undefined,
      undefined,
      undefined,
      "REF",
    );
  });
  test("getQuote on testnet builds a testnet client", async () => {
    await F.FolksAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 5, amount: BigInt(1), slippagePct: 0 },
      { network: "testnet", referrer: "", feeBps: 0 },
    );
    expect(window.FolksRouter.FolksRouterClient).toHaveBeenCalledWith("TEST");
  });
  test("buildSwapGroup decodes the prepared base64 group to bytes", async () => {
    const group = await F.FolksAdapter.buildSwapGroup(
      { raw: { params: {}, slippageBps: 50, swapQuote: {} } },
      "ADDR",
      { network: "mainnet" },
    );
    expect(group).toHaveLength(2);
    expect(Array.from(group[0])).toEqual([65, 66]); // "AB"
  });
});

describe("error branches", () => {
  afterEach(() => {
    delete global.fetch;
    delete window.asastatsSwap;
  });
  test("readPanelHoldings returns [] when island absent", () => {
    document.body.innerHTML = '<div class="id-swap-panel"></div>';
    expect(
      F.readPanelHoldings(document.querySelector(".id-swap-panel")),
    ).toEqual([]);
  });
  test("refreshQuote surfaces a quote error and disables the button", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "5";
    panel.querySelector(".id-swap-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => {
          throw new Error("no route");
        }),
      },
      quoteTimer: null,
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "no route",
    );
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(true);
  });
  test("executeSwap surfaces a signing failure", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "31566704";
    panel.querySelector(".id-swap-amount").value = "1";
    global.fetch = jest.fn(async () => ({
      text: async () =>
        panelHTML([
          { id: 0, amount: 5000000 },
          { id: 31566704, amount: 0 },
        ]),
    }));
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: jest.fn(),
      signAndSend: jest.fn(async () => {
        throw new Error("user rejected");
      }),
    };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn(async () => []) },
    };
    await F.executeSwap(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "user rejected",
    );
  });
  test("executeSwap no-ops without a quote", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "5";
    panel.querySelector(".id-swap-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: null,
      adapter: { buildSwapGroup: jest.fn() },
    };
    await F.executeSwap(panel, ctx);
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
  });
  test("renderQuote no-ops without an output element; setPanelStatus tolerates missing el", () => {
    const bare = document.createElement("div");
    expect(() =>
      F.renderQuote(bare, {
        amountOut: BigInt(1),
        minimumReceived: BigInt(1),
        priceImpactPct: 0,
        routeLabel: "x",
        feesTotal: 0,
      }),
    ).not.toThrow();
    expect(() => F.setPanelStatus(bare, "hi")).not.toThrow();
  });
});

describe("debounce + fetch edge", () => {
  afterEach(() => {
    delete global.fetch;
    jest.useRealTimers();
  });
  test("scheduleQuote debounces into refreshQuote when the timer fires", () => {
    jest.useFakeTimers();
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "5";
    panel.querySelector(".id-swap-amount").value = "1";
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          amountOut: BigInt(1),
          minimumReceived: BigInt(1),
          priceImpactPct: 0,
          routeLabel: "r",
          feesTotal: 0,
        })),
      },
      quoteTimer: null,
    };
    F.scheduleQuote(panel, ctx);
    expect(ctx.adapter.getQuote).not.toHaveBeenCalled();
    jest.advanceTimersByTime(400);
    expect(ctx.adapter.getQuote).toHaveBeenCalled();
  });
  test("fetchHoldings returns [] when the island holds bad JSON", async () => {
    global.fetch = jest.fn(async () => ({
      text: async () => '<script class="id-swap-holdings">{bad</script>',
    }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });
});

describe("applyImpliedSource", () => {
  function panelWith(ids) {
    document.body.innerHTML =
      '<div class="id-swap-panel"><select class="id-swap-from">' +
      ids.map((i) => `<option value="${i}">u</option>`).join("") +
      "</select></div>";
    return document.querySelector(".id-swap-panel");
  }

  test("selects the source option when the asset is held", () => {
    const panel = panelWith(["0", "31566704"]);
    expect(F.applyImpliedSource(panel, "31566704")).toBe(true);
    expect(panel.querySelector(".id-swap-from").value).toBe("31566704");
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
    document.body.innerHTML = '<div class="id-swap-panel"></div>';
    const panel = document.querySelector(".id-swap-panel");
    expect(F.applyImpliedSource(panel, "1")).toBe(false);
  });
});

describe("branch coverage", () => {
  function panel(html) {
    document.body.innerHTML = '<div class="id-swap-panel">' + html + "</div>";
    return document.querySelector(".id-swap-panel");
  }
  afterEach(() => {
    F.FolksAdapter._clients = {};
  });

  test("_clientFor: testnet network + client caching", () => {
    delete F.FolksAdapter._clients;
    const ClientCtor = jest.fn(function (net) {
      this.net = net;
    });
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
    expect(
      F.readPanelHoldings(panel('<script class="id-swap-holdings"></script>')),
    ).toEqual([]);
  });

  test("fetchHoldings: empty island -> []", async () => {
    global.fetch = jest.fn(async () => ({
      text: async () => '<script class="id-swap-holdings"></script>',
    }));
    await expect(F.fetchHoldings("/u")).resolves.toEqual([]);
  });

  test("selectTarget: missing decimals/unit defaults, no results node", () => {
    const p = panel(
      '<input class="id-swap-to" type="hidden">' +
        '<span class="id-swap-optin-notice"></span><input class="id-swap-to-search">',
    );
    const opt = document.createElement("div");
    opt.dataset.id = "31566704";
    F.selectTarget(p, opt, { quoteTimer: null });
    expect(p.querySelector(".id-swap-to").dataset.decimals).toBe("0");
    expect(p.querySelector(".id-swap-to").dataset.unit).toBe("");
    expect(p.querySelector(".id-swap-to-search").value).toBe("ASA (#31566704)");
  });

  test("readQuoteParams: default decimals + empty slippage", () => {
    const p = panel(
      '<select class="id-swap-from"><option value="0" data-amount="5000000">A</option></select>' +
        '<input class="id-swap-to" value="31566704"><input class="id-swap-amount" value="1">' +
        '<input class="id-swap-slippage" value="">',
    );
    expect(F.readQuoteParams(p, "ADDR").slippagePct).toBe(0.5);
  });

  test("refreshQuote: incomplete form, no button", async () => {
    const p = panel(
      '<select class="id-swap-from"></select><input class="id-swap-to" value="">' +
        '<input class="id-swap-amount" value=""><input class="id-swap-slippage" value="0.5">',
    );
    await F.refreshQuote(p, { owns: true });
  });

  test("refreshQuote: success, no button", async () => {
    const p = panel(
      '<select class="id-swap-from"><option value="0" data-decimals="6">A</option></select>' +
        '<input class="id-swap-to" value="31566704"><input class="id-swap-amount" value="1">' +
        '<input class="id-swap-slippage" value="0.5"><div class="id-swap-status"></div>',
    );
    const adapter = {
      getQuote: jest
        .fn()
        .mockResolvedValue({
          amountOut: 1n,
          minimumReceived: 1n,
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "X",
        }),
    };
    await F.refreshQuote(p, { adapter, cfg: {}, owns: true });
    expect(adapter.getQuote).toHaveBeenCalled();
  });

  test("refreshQuote: error, no button", async () => {
    const p = panel(
      '<select class="id-swap-from"><option value="0" data-decimals="6">A</option></select>' +
        '<input class="id-swap-to" value="31566704"><input class="id-swap-amount" value="1">' +
        '<input class="id-swap-slippage" value="0.5"><div class="id-swap-status"></div>',
    );
    await F.refreshQuote(p, {
      adapter: { getQuote: jest.fn().mockRejectedValue(new Error("boom")) },
      cfg: {},
      owns: true,
    });
    expect(p.querySelector(".id-swap-status").textContent).toContain("boom");
  });

  test("executeSwap: no button, insufficient balance hits finally", async () => {
    global.fetch = jest.fn(async () => ({
      text: async () =>
        '<script class="id-swap-holdings">[{"id":0,"amount":"1"}]</script>',
    }));
    const p = panel(
      '<select class="id-swap-from"><option value="0" data-decimals="6">A</option></select>' +
        '<input class="id-swap-to" value="31566704"><input class="id-swap-amount" value="1">' +
        '<input class="id-swap-slippage" value="0.5"><div class="id-swap-status"></div>',
    );
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    await F.executeSwap(p, {
      adapter: {},
      cfg: {},
      fromAddress: "ADDR",
      owns: true,
      lastQuote: {},
      holdingsUrl: "/u",
    });
    expect(p.querySelector(".id-swap-status").textContent).toContain(
      "Insufficient",
    );
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
      '<div class="id-swap-panel"><span class="id-swap-cfg" data-router="folks"' +
      ' data-network="testnet" data-referrer="REF" data-fee-bps="25"></span></div>';
    const cfg = F.readPanelCfg(document.querySelector(".id-swap-panel"));
    expect(cfg).toEqual({
      router: "folks",
      network: "testnet",
      referrer: "REF",
      feeBps: 25,
      explorerBase: "",
      explorerTxPath: "",
    });
  });

  test("readPanelCfg: defaults when attrs missing", () => {
    document.body.innerHTML =
      '<div class="id-swap-panel"><span class="id-swap-cfg"></span></div>';
    expect(F.readPanelCfg(document.querySelector(".id-swap-panel"))).toEqual({
      router: "",
      network: "mainnet",
      referrer: "",
      feeBps: 0,
      explorerBase: "",
      explorerTxPath: "",
    });
  });

  test("readPanelCfg: null when no island", () => {
    document.body.innerHTML = '<div class="id-swap-panel"></div>';
    expect(F.readPanelCfg(document.querySelector(".id-swap-panel"))).toBeNull();
  });

  test("inlineHoldingsUrl: fills address + from", () => {
    expect(
      F.inlineHoldingsUrl(
        "/widgets/folks/ADDRESS/holdings",
        "AAAA",
        "31566704",
      ),
    ).toBe("/widgets/folks/AAAA/holdings?from=31566704");
  });

  test("inlineHoldingsUrl: omits from when absent", () => {
    expect(
      F.inlineHoldingsUrl("/widgets/folks/ADDRESS/holdings", "AAAA", null),
    ).toBe("/widgets/folks/AAAA/holdings");
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
    wrap.className = "id-swap-form";
    const sel = document.createElement("select");
    sel.className = "id-swap-from";
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
    amount.className = "id-swap-amount";
    wrap.appendChild(amount);
    return wrap;
  }

  test("markerCfg: null -> null", () => {
    expect(F.markerCfg(null)).toBeNull();
  });
  test("markerCfg: defaults when only router set", () => {
    const m = document.createElement("span");
    m.dataset.router = "folks";
    // ADDED apiKey: "" to match updated return object
    expect(F.markerCfg(m)).toEqual({
      router: "folks",
      network: "mainnet",
      referrer: "",
      feeBps: 0,
      apiKey: "",
    });
  });
  test("markerCfg: explicit network/referrer/feeBps", () => {
    const m = document.createElement("span");
    m.dataset.router = "folks";
    m.dataset.network = "testnet";
    m.dataset.referrer = "ADDR";
    m.dataset.feeBps = "30";
    // ADDED apiKey: "" to match updated return object
    expect(F.markerCfg(m)).toEqual({
      router: "folks",
      network: "testnet",
      referrer: "ADDR",
      feeBps: 30,
      apiKey: "",
    });
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
    expect(
      F.sourceHoldingsBaseUnits(makePanel({ withOption: false })),
    ).toBeNull();
  });
  test("sourceHoldingsBaseUnits: null when option lacks data-amount", () => {
    expect(F.sourceHoldingsBaseUnits(makePanel({ amount: null }))).toBeNull();
  });

  test("setAmountFromPercent: writes field, returns value", () => {
    const p = makePanel();
    expect(F.setAmountFromPercent(p, 75)).toBe("750");
    expect(p.querySelector(".id-swap-amount").value).toBe("750");
  });
  test("setAmountFromPercent: '' when holdings unresolved", () => {
    expect(F.setAmountFromPercent(makePanel({ amount: null }), 50)).toBe("");
  });
  test("setAmountFromPercent: '' when amount field missing", () => {
    const p = makePanel();
    p.querySelector(".id-swap-amount").remove();
    expect(F.setAmountFromPercent(p, 50)).toBe("");
  });

  test("applySwapMode: null form -> 'sell'", () => {
    expect(F.applySwapMode(null, "buy")).toBe("sell");
  });
  test("applySwapMode: buy adds class, sell removes it", () => {
    const f = document.createElement("div");
    expect(F.applySwapMode(f, "buy")).toBe("buy");
    expect(f.classList.contains("swap-mode-buy")).toBe(true);
    expect(F.applySwapMode(f, "sell")).toBe("sell");
    expect(f.classList.contains("swap-mode-buy")).toBe(false);
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
    sel.className = "id-swap-from";
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
    sel.className = "id-swap-from";
    const o = document.createElement("option");
    o.value = "1";
    o.dataset.amount = "250"; // no data-decimals -> `|| "0"`
    sel.appendChild(o);
    wrap.appendChild(sel);
    const amount = document.createElement("input");
    amount.className = "id-swap-amount";
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
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(true); // reveal
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(false); // hide
    expect(F.toggleInlineSwap(wrap, null, labels)).toBe(true); // reveal
    expect(wrap.classList.contains("hidden")).toBe(false);
  });

  test("returns a strict boolean", () => {
    document.body.innerHTML = '<div id="w" class="hidden"></div>';
    expect(
      typeof F.toggleInlineSwap(document.getElementById("w"), null, labels),
    ).toBe("boolean");
  });
});
describe("swap success + dirty helpers", () => {
  test("txExplorerUrl builds the explorer URL (and encodes)", () => {
    expect(F.txExplorerUrl("ABC123")).toBe("https://allo.info/tx/ABC123");
    expect(F.txExplorerUrl("a/b c")).toBe("https://allo.info/tx/a%2Fb%20c");
  });

  test("txExplorerUrl honours a base/path override", () => {
    expect(
      F.txExplorerUrl("TX", "https://lora.algokit.io/mainnet/", "transaction/"),
    ).toBe("https://lora.algokit.io/mainnet/transaction/TX");
  });

  test("alloTxUrl alias still resolves to the default (Allo)", () => {
    expect(F.alloTxUrl("TX")).toBe("https://allo.info/tx/TX");
  });

  function panelWith() {
    const p = document.createElement("div");
    p.innerHTML =
      '<div class="id-swap-status"></div>' +
      '<input class="id-swap-amount" value="1.5">' +
      '<input class="id-swap-pct" value="50">' +
      '<div class="id-swap-quote">≈ 100</div>';
    return p;
  }

  test("renderSwapSuccess: uses the panel's explorer cfg when present", () => {
    const p = panelWith();
    const cfg = document.createElement("div");
    cfg.className = "id-swap-cfg";
    cfg.dataset.explorerBase = "https://lora.algokit.io/mainnet/";
    cfg.dataset.explorerTxPath = "transaction/";
    p.appendChild(cfg);
    F.renderSwapSuccess(p, "TXID");
    const link = p.querySelector(".id-swap-tx-link");
    expect(link.getAttribute("href")).toBe(
      "https://lora.algokit.io/mainnet/transaction/TXID",
    );
  });

  test("renderSwapSuccess: falls back to the swap root explorer cfg", () => {
    const root = document.createElement("div");
    root.id = "id-swap-swap";
    root.dataset.explorerBase = "https://algo.surf/";
    root.dataset.explorerTxPath = "transaction/";
    const p = panelWith();
    root.appendChild(p);
    F.renderSwapSuccess(p, "TXID");
    const link = p.querySelector(".id-swap-tx-link");
    expect(link.getAttribute("href")).toBe(
      "https://algo.surf/transaction/TXID",
    );
  });

  test("renderSwapSuccess: builds link and resets amount/pct/quote", () => {
    const p = panelWith();
    F.renderSwapSuccess(p, "TXID");
    const link = p.querySelector(".id-swap-tx-link");
    expect(link.getAttribute("href")).toBe("https://allo.info/tx/TXID");
    expect(link.textContent).toBe("TXID");
    expect(link.target).toBe("_blank");
    expect(p.querySelector(".id-swap-status").textContent).toBe(
      "Swap submitted: TXID",
    );
    expect(p.querySelector(".id-swap-amount").value).toBe("");
    expect(p.querySelector(".id-swap-pct").value).toBe("");
    expect(p.querySelector(".id-swap-quote").textContent).toBe("");
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
    expect(modal.dataset.swapDirty).toBe("1");
  });

  test("markSwapDirty: no-op when not inside a modal", () => {
    expect(F.markSwapDirty(document.createElement("div"))).toBe(false);
  });
});

describe("getQuote discount handling", () => {
  function clientMock(discountImpl) {
    const client = {
      fetchSwapQuote: jest.fn(async () => ({
        quoteAmount: BigInt(2000000),
        priceImpact: 0.1,
        microalgoTxnsFee: 2000,
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
  beforeEach(() => {
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
  });
  afterEach(() => {
    delete window.FolksRouter;
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
  });

  test("fetches the user discount and passes it (no feeBps)", async () => {
    const client = clientMock();
    await F.FolksAdapter.getQuote(
      {
        fromAssetId: 0,
        toAssetId: 5,
        amount: BigInt(1),
        slippagePct: 0,
        fromAddress: "USER",
      },
      { network: "mainnet", referrer: "REF" },
    );
    expect(client.fetchUserDiscount).toHaveBeenCalledWith("USER");
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.objectContaining({ fromAssetId: 0, toAssetId: 5 }),
      undefined,
      undefined,
      10,
      "REF",
    );
  });
  test("caches the discount per address (one lookup across quotes)", async () => {
    delete F.FolksAdapter._discounts; // exercise lazy-init
    const client = clientMock();
    const p = {
      fromAssetId: 0,
      toAssetId: 5,
      amount: BigInt(1),
      slippagePct: 0,
      fromAddress: "USER",
    };
    await F.FolksAdapter.getQuote(p, { network: "mainnet" });
    await F.FolksAdapter.getQuote(p, { network: "mainnet" });
    expect(client.fetchUserDiscount).toHaveBeenCalledTimes(1);
  });
  test("a discount lookup failure does not block the quote", async () => {
    const client = clientMock(
      jest.fn(async () => {
        throw new Error("down");
      }),
    );
    const q = await F.FolksAdapter.getQuote(
      {
        fromAssetId: 0,
        toAssetId: 5,
        amount: BigInt(1),
        slippagePct: 0,
        fromAddress: "USER",
      },
      { network: "mainnet" },
    );
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(client.fetchSwapQuote).toHaveBeenCalledWith(
      expect.anything(),
      undefined,
      undefined,
      undefined,
      undefined,
    );
  });
});

describe("walletOwns + applyOwnership", () => {
  afterEach(() => {
    delete window.asastatsSwap;
  });
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
      '<button class="id-swap-swap-btn" disabled></button>' +
      '<div class="id-swap-connect-notice" style="display:none;"></div>';
    return p;
  }
  test("applyOwnership(true): enables button, hides notice", () => {
    const p = ownPanel();
    expect(F.applyOwnership(p, true)).toBe(true);
    expect(p.querySelector(".id-swap-swap-btn").disabled).toBe(false);
    expect(p.querySelector(".id-swap-connect-notice").style.display).toBe(
      "none",
    );
  });
  test("applyOwnership(false): disables button, shows notice", () => {
    const p = ownPanel();
    F.applyOwnership(p, false);
    expect(p.querySelector(".id-swap-swap-btn").disabled).toBe(true);
    expect(p.querySelector(".id-swap-connect-notice").style.display).toBe(
      "block",
    );
  });
  test("applyOwnership tolerates missing button/notice", () => {
    expect(() =>
      F.applyOwnership(document.createElement("div"), true),
    ).not.toThrow();
  });
});

describe("executeSwap ownership gate", () => {
  afterEach(() => {
    delete global.fetch;
    delete window.asastatsSwap;
  });
  test("does not build/sign when the wallet is not the from-address", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "31566704";
    panel.querySelector(".id-swap-amount").value = "1";
    window.asastatsSwap = {
      activeAddress: () => "OTHER",
      optIn: jest.fn(),
      signAndSend: jest.fn(),
    };
    global.fetch = jest.fn();
    const ctx = {
      fromAddress: "ADDR",
      owns: false,
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: { buildSwapGroup: jest.fn() },
    };
    await F.executeSwap(panel, ctx);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(ctx.adapter.buildSwapGroup).not.toHaveBeenCalled();
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "Connect the wallet",
    );
  });
});

describe("inlineHoldingsUrl encoding", () => {
  test("encodes the from-asset query value", () => {
    expect(F.inlineHoldingsUrl("/w/ADDRESS/h", "ADDR", "a b&c")).toBe(
      "/w/ADDR/h?from=a%20b%26c",
    );
  });
  test("numeric from-asset is unchanged", () => {
    expect(F.inlineHoldingsUrl("/w/ADDRESS/h", "ADDR", "123")).toBe(
      "/w/ADDR/h?from=123",
    );
  });
});

describe("shared quote helpers", () => {
  test("minReceived applies slippage bps (fixed-input)", () => {
    expect(F.minReceived(BigInt(2000000), 0.5)).toBe(BigInt(1990000)); // 50 bps
    expect(F.minReceived(BigInt(2000000), 0)).toBe(BigInt(2000000));
  });
  test("routeLabelFrom joins protocol keys, '' when empty/absent", () => {
    expect(F.routeLabelFrom({ TinymanV2: 60, Pact: 40 })).toBe(
      "TinymanV2, Pact",
    );
    expect(F.routeLabelFrom({})).toBe("");
    expect(F.routeLabelFrom(null)).toBe("");
  });
  test("makeQuote fills defaults for optional fields", () => {
    const q = F.makeQuote({
      amountOut: BigInt(1),
      minimumReceived: BigInt(1),
      routeLabel: "X",
    });
    expect(q.priceImpactPct).toBe(0);
    expect(q.feesTotal).toBe(0);
    expect(q.raw).toEqual({});
  });
});

describe("HaystackAdapter", () => {
  let client;
  beforeEach(() => {
    F.HaystackAdapter._clients = {};
    client = {
      newQuote: jest.fn(async () => ({
        quote: "2000000",
        userPriceImpact: 0.2,
        flattenedRoute: { TinymanV2: 100 },
      })),
      newSwap: jest.fn(async () => ({
        execute: jest.fn(async () => ({ confirmedRound: 9n, txIds: ["HSTX"] })),
      })),
    };
    window.HaystackRouter = { RouterClient: jest.fn(() => client) };
  });
  afterEach(() => {
    delete window.HaystackRouter;
    F.HaystackAdapter._clients = {};
  });

  test("_clientFor: constructs with apiKey+referrer+autoOptIn, no feeBps; caches per key", () => {
    const c1 = F.HaystackAdapter._clientFor({ apiKey: "K", referrer: "REF" });
    const c2 = F.HaystackAdapter._clientFor({ apiKey: "K", referrer: "REF" });
    expect(c1).toBe(c2);
    expect(window.HaystackRouter.RouterClient).toHaveBeenCalledTimes(1);
    const arg = window.HaystackRouter.RouterClient.mock.calls[0][0];
    expect(arg).toEqual({
      apiKey: "K",
      referrerAddress: "REF",
      autoOptIn: true,
    });
    expect("feeBps" in arg).toBe(false);
  });
  test("_clientFor: lazy-inits the cache", () => {
    delete F.HaystackAdapter._clients;
    expect(F.HaystackAdapter._clientFor({ apiKey: "K" })).toBeDefined();
  });
  test("getQuote: normalises quote, min-received, route label, raw payload", async () => {
    const q = await F.HaystackAdapter.getQuote(
      {
        fromAssetId: 0,
        toAssetId: 31566704,
        amount: BigInt(1000000),
        slippagePct: 1,
        fromAddress: "USER",
      },
      { apiKey: "K", referrer: "REF" },
    );
    expect(client.newQuote).toHaveBeenCalledWith({
      address: "USER",
      fromASAID: 0,
      toASAID: 31566704,
      amount: BigInt(1000000),
      type: "fixed-input",
    });
    expect(q.amountOut).toBe(BigInt(2000000));
    expect(q.minimumReceived).toBe(BigInt(1980000)); // 1% = 100 bps
    expect(q.priceImpactPct).toBe(0.2);
    expect(q.routeLabel).toBe("TinymanV2");
    expect(q.raw.slippagePct).toBe(1);
  });
  test("getQuote: falls back to market price impact + default label", async () => {
    client.newQuote = jest.fn(async () => ({
      quote: "5",
      marketPriceImpact: 0.9,
      flattenedRoute: {},
    }));
    const q = await F.HaystackAdapter.getQuote(
      { fromAssetId: 0, toAssetId: 1, amount: BigInt(5), slippagePct: 0 },
      { apiKey: "K" },
    );
    expect(q.priceImpactPct).toBe(0.9);
    expect(q.routeLabel).toBe("Haystack Router");
  });
  test("executeSwap: composes via the bridge signer and returns the txid", async () => {
    const bridge = { haystackSigner: jest.fn() };
    const txid = await F.HaystackAdapter.executeSwap(
      {
        quote: { raw: { swapQuote: { q: 1 }, slippagePct: 1 } },
        fromAddress: "USER",
        cfg: { apiKey: "K" },
      },
      bridge,
    );
    expect(client.newSwap).toHaveBeenCalledWith({
      quote: { q: 1 },
      address: "USER",
      slippage: 1,
      signer: bridge.haystackSigner,
    });
    expect(txid).toBe("HSTX");
  });
  test("executeSwap: empty txid when the composer returns none", async () => {
    client.newSwap = jest.fn(async () => ({
      execute: jest.fn(async () => ({ txIds: [] })),
    }));
    const txid = await F.HaystackAdapter.executeSwap(
      {
        quote: { raw: { swapQuote: {}, slippagePct: 0 } },
        fromAddress: "USER",
        cfg: {},
      },
      { signer: jest.fn() },
    );
    expect(txid).toBe("");
  });
});

describe("controller executeSwap delegates to router-owned execution", () => {
  afterEach(() => {
    delete global.fetch;
    delete window.asastatsSwap;
  });
  test("uses adapter.executeSwap (no separate opt-in) when provided", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    panel.querySelector(".id-swap-to").value = "31566704";
    panel.querySelector(".id-swap-amount").value = "1";
    global.fetch = jest.fn(async () => ({
      text: async () => panelHTML([{ id: 0, amount: 5000000 }]),
    })); // target absent => would opt-in on legacy path
    const optIn = jest.fn();
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      optIn: optIn,
      signer: jest.fn(),
    };
    const adapter = { executeSwap: jest.fn(async () => "HSTX") };
    const ctx = {
      fromAddress: "ADDR",
      owns: true,
      cfg: { apiKey: "K" },
      holdingsUrl: "/u",
      lastQuote: { raw: {} },
      adapter: adapter,
    };
    await F.executeSwap(panel, ctx);
    expect(adapter.executeSwap).toHaveBeenCalled();
    expect(optIn).not.toHaveBeenCalled(); // Haystack handles opt-in itself
    expect(panel.querySelector(".id-swap-tx-link").getAttribute("href")).toBe(
      "https://allo.info/tx/HSTX",
    );
  });
});
describe("fixed-output (buy) mode", () => {
  test("maxSent pads the input by slippage bps", () => {
    expect(F.maxSent(BigInt(1000000), 0.5)).toBe(BigInt(1005000));
    expect(F.maxSent(BigInt(1000000), 0)).toBe(BigInt(1000000));
  });

  test("readQuoteParams: buy uses TARGET decimals and tags mode", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "31566704";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1.5";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    const p = F.readQuoteParams(panel, "ADDR");
    expect(p.mode).toBe("buy");
    expect(p.amount).toBe(BigInt(1500000)); // 1.5 in TO (6) decimals
  });

  test("FolksAdapter.getQuote buy: required input + max sent + FIXED_OUTPUT", async () => {
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
    mockFolksRouter({
      quote: {
        quoteAmount: 2000000n,
        priceImpact: 0.1,
        microalgoTxnsFee: 3000,
        txnPayload: "P",
      },
    });
    const q = await F.FolksAdapter.getQuote(
      {
        mode: "buy",
        fromAssetId: 0,
        toAssetId: 5,
        amount: BigInt(1000000),
        slippagePct: 0.5,
      },
      { network: "mainnet", referrer: "REF" },
    );
    expect(q.mode).toBe("buy");
    expect(q.amountIn).toBe(BigInt(2000000)); // quoteAmount = required input
    expect(q.amountOut).toBe(BigInt(1000000)); // the fixed target
    expect(q.maximumSent).toBe(BigInt(2010000)); // +50 bps
    expect(
      F.FolksAdapter._clients.mainnet.fetchSwapQuote.mock.calls[0][0].swapMode,
    ).toBe("FIXED_OUTPUT");
    delete window.FolksRouter;
    F.FolksAdapter._clients = {};
    F.FolksAdapter._discounts = {};
  });

  test("HaystackAdapter.getQuote buy: type fixed-output, required input + max sent", async () => {
    F.HaystackAdapter._clients = {};
    const client = {
      newQuote: jest.fn(async () => ({
        quote: "2000000",
        userPriceImpact: 0.2,
        flattenedRoute: { Pact: 100 },
      })),
    };
    window.HaystackRouter = { RouterClient: jest.fn(() => client) };
    const q = await F.HaystackAdapter.getQuote(
      {
        mode: "buy",
        fromAssetId: 0,
        toAssetId: 5,
        amount: BigInt(1000000),
        slippagePct: 1,
      },
      { apiKey: "K" },
    );
    expect(client.newQuote.mock.calls[0][0].type).toBe("fixed-output");
    expect(q.mode).toBe("buy");
    expect(q.amountIn).toBe(BigInt(2000000));
    expect(q.maximumSent).toBe(BigInt(2020000)); // +100 bps
    delete window.HaystackRouter;
    F.HaystackAdapter._clients = {};
  });

  test("renderQuote buy: shows required input + max in source units", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0"; // ALGO, 6dp
    F.renderQuote(panel, {
      mode: "buy",
      amountIn: BigInt(2000000),
      maximumSent: BigInt(2010000),
      amountOut: BigInt(1000000),
      priceImpactPct: 0.1,
      feesTotal: 3000,
      routeLabel: "Folks Router",
    });
    const txt = panel.querySelector(".id-swap-quote").textContent;
    expect(txt).toContain("2 ALGO");
    expect(txt).toContain("(max 2.01");
    expect(txt).toContain("via Folks Router");
  });

  test("affordabilityError: sell '', buy ok '', buy short message, no holdings ''", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0"; // 5 ALGO held
    expect(F.affordabilityError(panel, { mode: "sell" })).toBe(""); // no amountIn
    expect(
      F.affordabilityError(panel, { mode: "sell", amountIn: BigInt(2000000) }),
    ).toBe(""); // 2 <= 5
    const sellMsg = F.affordabilityError(panel, {
      mode: "sell",
      amountIn: BigInt(6000000),
    });
    expect(sellMsg).toContain("You only have 5 ALGO");
    expect(sellMsg).toContain("tried to sell 6 ALGO");
    expect(
      F.affordabilityError(panel, {
        mode: "buy",
        maximumSent: BigInt(2010000),
      }),
    ).toBe("");
    const msg = F.affordabilityError(panel, {
      mode: "buy",
      maximumSent: BigInt(6000000),
    });
    expect(msg).toContain("Need up to 6 ALGO");
    expect(msg).toContain("you have 5 ALGO");
    panel.querySelector(".id-swap-from").value = "";
    expect(
      F.affordabilityError(panel, { mode: "buy", maximumSent: BigInt(1) }),
    ).toBe("");
  });

  test("refreshQuote buy: blocks swap when required input exceeds holdings", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "5";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "buy",
          amountIn: BigInt(6000000),
          maximumSent: BigInt(6000000),
          amountOut: BigInt(1000000),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "R",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "Need up to 6 ALGO",
    );
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(true);
    delete window.asastatsSwap;
  });

  test("executeSwap buy: insufficient when max-sent exceeds fresh holdings", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "5";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    global.fetch = jest.fn(async () => ({
      text: async () => panelHTML([{ id: 0, amount: 5000000 }]),
    }));
    window.asastatsSwap = {
      activeAddress: () => "ADDR",
      signAndSend: jest.fn(),
    };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      holdingsUrl: "/u",
      lastQuote: {
        mode: "buy",
        maximumSent: BigInt(6000000),
        amountOut: BigInt(1000000),
      },
      adapter: { buildSwapGroup: jest.fn() },
    };
    await F.executeSwap(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "Insufficient",
    );
    expect(window.asastatsSwap.signAndSend).not.toHaveBeenCalled();
    delete global.fetch;
    delete window.asastatsSwap;
  });
});

describe("fixed-output (buy) — fallback branches", () => {
  test("readQuoteParams buy: empty TO decimals falls back to 0", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "5"; // to.dataset.decimals stays "" -> fallback "0"
    panel.querySelector(".id-swap-amount").value = "3";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    const p = F.readQuoteParams(panel, "ADDR");
    expect(p.mode).toBe("buy");
    expect(p.amount).toBe(BigInt(3)); // 3 in 0 decimals
  });

  test("refreshQuote buy: unaffordable with no swap button does not throw", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-swap-btn").remove();
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "5";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "buy",
          amountIn: BigInt(6000000),
          maximumSent: BigInt(6000000),
          amountOut: BigInt(1000000),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "R",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "Need up to 6 ALGO",
    );
    delete window.asastatsSwap;
  });

  test("renderQuote buy: no selected from-option falls back to 0 decimals / '' unit", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = ""; // no selection -> fromOpt undefined
    F.renderQuote(panel, {
      mode: "buy",
      amountIn: BigInt(2),
      maximumSent: BigInt(3),
      amountOut: BigInt(1),
      priceImpactPct: 0,
      feesTotal: 0,
      routeLabel: "R",
    });
    const txt = panel.querySelector(".id-swap-quote").textContent;
    expect(txt).toContain("≈ 2 "); // raw base units (0 decimals), empty unit
  });

  test("affordabilityError buy-short: empty from dataset falls back", () => {
    const panel = mountPanel([]);
    const opt = panel.querySelector(".id-swap-from").options[0];
    opt.dataset.decimals = "";
    opt.dataset.unit = ""; // keep data-amount=5000000
    panel.querySelector(".id-swap-from").value = "0";
    const msg = F.affordabilityError(panel, {
      mode: "buy",
      maximumSent: BigInt(6000000),
    });
    expect(msg).toContain("Need up to 6000000"); // 0-decimals fallback, no unit
  });
});

describe("retargetForMode (anchor flips From<->To)", () => {
  function twoAssetPanel(anchorFirst) {
    const panel = mountPanel([]);
    const sel = panel.querySelector(".id-swap-from");
    const usdc =
      '<option value="31566704" data-decimals="6" data-unit="USDC" data-amount="5000000">USDC</option>';
    const algo =
      '<option value="0" data-decimals="6" data-unit="ALGO" data-amount="3000000">ALGO</option>';
    sel.innerHTML = anchorFirst ? usdc + algo : algo + usdc;
    sel.value = "31566704"; // anchor = USDC (the clicked asset)
    return panel;
  }

  test("buy: anchor becomes the locked To, From defaults to a non-anchor holding", () => {
    const panel = twoAssetPanel(true);
    const res = F.retargetForMode(panel, "buy");
    expect(res).toEqual({ mode: "buy", ok: true });
    const to = panel.querySelector(".id-swap-to");
    expect(to.value).toBe("31566704"); // To locked to anchor (USDC)
    expect(to.dataset.decimals).toBe("6");
    expect(to.dataset.unit).toBe("USDC");
    expect(panel.querySelector(".id-swap-from").value).toBe("0"); // source = ALGO
    const search = panel.querySelector(".id-swap-to-search");
    expect(search.value).toBe(""); // empty so typing searches cleanly
    expect(search.placeholder).toContain("USDC");
    expect(search.placeholder).toContain("#31566704");
    expect(panel.dataset.anchorId).toBe("31566704");
  });

  test("sell after buy: restores From=anchor and frees the To picker", () => {
    const panel = twoAssetPanel(true);
    F.retargetForMode(panel, "buy"); // sets dataset.anchorId
    const res = F.retargetForMode(panel, "sell");
    expect(res).toEqual({ mode: "sell", ok: true });
    expect(panel.querySelector(".id-swap-from").value).toBe("31566704"); // back to USDC
    const to = panel.querySelector(".id-swap-to");
    expect(to.value).toBe("");
    expect(to.dataset.decimals).toBe("");
    const search = panel.querySelector(".id-swap-to-search");
    expect(search.value).toBe("");
    expect(search.hasAttribute("readonly")).toBe(false);
  });

  test("buy with only the anchor held: reports no-source", () => {
    const panel = mountPanel([]);
    const sel = panel.querySelector(".id-swap-from");
    sel.innerHTML =
      '<option value="31566704" data-decimals="6" data-unit="USDC" data-amount="5000000">USDC</option>';
    sel.value = "31566704";
    expect(F.retargetForMode(panel, "buy")).toEqual({
      mode: "buy",
      ok: false,
      reason: "no-source",
    });
  });

  test("buy when the anchor id is not an option: falls back to 0/empty + picks first source", () => {
    const panel = twoAssetPanel(true);
    panel.dataset.anchorId = "999"; // remembered anchor no longer in the option list
    const res = F.retargetForMode(panel, "buy");
    expect(res.ok).toBe(true);
    const to = panel.querySelector(".id-swap-to");
    expect(to.value).toBe("999");
    expect(to.dataset.decimals).toBe("0"); // anchorOpt absent -> fallback
    expect(to.dataset.unit).toBe("");
    expect(panel.querySelector(".id-swap-to-search").placeholder).toContain(
      "#999",
    );
    expect(panel.querySelector(".id-swap-from").value).toBe("31566704"); // first != 999
  });

  test("anchorId falls back to '' when no From value and no stored anchor", () => {
    const panel = mountPanel([]);
    const sel = panel.querySelector(".id-swap-from");
    sel.innerHTML = '<option value="" >--</option>';
    sel.value = "";
    F.retargetForMode(panel, "sell");
    expect(panel.dataset.anchorId).toBe("");
  });
});

describe("updateSourceMax (max-owned in helper text)", () => {
  function panelWithMax() {
    const panel = mountPanel([]);
    panel.insertAdjacentHTML(
      "beforeend",
      '<span class="id-swap-from-max"></span>',
    );
    return panel;
  }
  test("writes the selected source holdings into the helper span", () => {
    const panel = panelWithMax();
    panel.querySelector(".id-swap-from").value = "0"; // ALGO 6dp, amount 5000000
    F.updateSourceMax(panel);
    expect(panel.querySelector(".id-swap-from-max").textContent).toBe(
      " — 5 ALGO",
    );
  });
  test("clears the span when the option has no amount", () => {
    const panel = panelWithMax();
    const opt = panel.querySelector(".id-swap-from").options[0];
    delete opt.dataset.amount;
    panel.querySelector(".id-swap-from").value = "0";
    F.updateSourceMax(panel);
    expect(panel.querySelector(".id-swap-from-max").textContent).toBe("");
  });
  test("no-ops when the helper span is absent", () => {
    const panel = mountPanel([]); // no .id-swap-from-max
    expect(() => F.updateSourceMax(panel)).not.toThrow();
  });
});

describe("fixed-output / max — remaining guards", () => {
  test("affordabilityError returns '' for a null quote", () => {
    expect(F.affordabilityError(mountPanel([]), null)).toBe("");
  });
  test("affordabilityError returns '' for a buy quote with no maximumSent", () => {
    expect(F.affordabilityError(mountPanel([]), { mode: "buy" })).toBe("");
  });
  test("updateSourceMax falls back to 0 decimals / '' unit", () => {
    const panel = mountPanel([]);
    panel.insertAdjacentHTML(
      "beforeend",
      '<span class="id-swap-from-max"></span>',
    );
    const opt = panel.querySelector(".id-swap-from").options[0];
    opt.dataset.decimals = "";
    opt.dataset.unit = ""; // amount stays 5000000
    panel.querySelector(".id-swap-from").value = "0";
    F.updateSourceMax(panel);
    expect(panel.querySelector(".id-swap-from-max").textContent).toBe(
      " — 5000000 ",
    );
  });
});

describe("empty / no-route quote handling", () => {
  test("quoteIsEmpty: true for null, zero output (sell), zero input (buy)", () => {
    expect(F.quoteIsEmpty(null)).toBe(true);
    expect(F.quoteIsEmpty({ mode: "sell", amountOut: BigInt(0) })).toBe(true);
    expect(F.quoteIsEmpty({ mode: "buy", amountIn: BigInt(0) })).toBe(true);
    expect(F.quoteIsEmpty({ mode: "buy" })).toBe(true); // missing amountIn
    expect(F.quoteIsEmpty({ mode: "sell", amountOut: BigInt(5) })).toBe(false);
    expect(F.quoteIsEmpty({ mode: "buy", amountIn: BigInt(5) })).toBe(false);
  });

  test("refreshQuote: an all-zero router quote shows 'no route' and disables swap", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "393537671";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "10000";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "buy",
          amountIn: BigInt(0),
          maximumSent: BigInt(0),
          amountOut: BigInt(10000000000),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "Haystack Router",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "No route available",
    );
    expect(panel.querySelector(".id-swap-swap-btn").disabled).toBe(true);
    expect(panel.querySelector(".id-swap-quote").textContent).toBe(""); // never rendered "≈ 0"
    delete window.asastatsSwap;
  });
});

describe("empty quote — no button branch", () => {
  test("refreshQuote: empty quote with no swap button does not throw", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-swap-btn").remove();
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "5";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "10000";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "buy",
          amountIn: BigInt(0),
          maximumSent: BigInt(0),
          amountOut: BigInt(1),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "R",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-status").textContent).toContain(
      "No route available",
    );
    delete window.asastatsSwap;
  });
});

describe("Haystack fixed-output: amount is sent unmodified in target base units", () => {
  test("buy 10000 of a 6-decimal asset -> amount = 10000 * 1e6 (decimals correct)", async () => {
    F.HaystackAdapter._clients = {};
    let captured;
    const client = {
      newQuote: jest.fn(async (p) => {
        captured = p;
        return { quote: "1350000", flattenedRoute: {} };
      }),
    };
    window.HaystackRouter = { RouterClient: jest.fn(() => client) };
    const q = await F.HaystackAdapter.getQuote(
      {
        mode: "buy",
        fromAssetId: 0,
        toAssetId: 393537671,
        amount: BigInt(10000) * BigInt(1000000),
        slippagePct: 0.5,
      },
      { apiKey: "K" },
    );
    expect(captured.type).toBe("fixed-output");
    expect(captured.toASAID).toBe(393537671);
    expect(captured.amount).toBe(BigInt(10000000000)); // sent verbatim, in target base units
    expect(q.amountIn).toBe(BigInt(1350000)); // required input read back from sq.quote
    delete window.HaystackRouter;
    F.HaystackAdapter._clients = {};
  });

  test("an empty/zero router response is detected as no-route (not rendered as 0)", async () => {
    F.HaystackAdapter._clients = {};
    // The SDK maps an empty API quote ("") to 0n before our adapter sees it.
    const client = {
      newQuote: jest.fn(async () => ({ quote: "0", flattenedRoute: {} })),
    };
    window.HaystackRouter = { RouterClient: jest.fn(() => client) };
    const q = await F.HaystackAdapter.getQuote(
      {
        mode: "buy",
        fromAssetId: 0,
        toAssetId: 393537671,
        amount: BigInt(10000000000),
        slippagePct: 0.5,
      },
      { apiKey: "K" },
    );
    expect(F.quoteIsEmpty(q)).toBe(true);
    delete window.HaystackRouter;
    F.HaystackAdapter._clients = {};
  });
});

describe("status styling + stale-quote clearing", () => {
  test("setPanelStatus toggles the error class on/off", () => {
    const panel = mountPanel([]);
    const status = panel.querySelector(".id-swap-status");
    F.setPanelStatus(panel, "oops", true);
    expect(status.textContent).toBe("oops");
    expect(status.classList.contains("id-swap-status-error")).toBe(true);
    F.setPanelStatus(panel, "ok"); // not an error -> class removed
    expect(status.classList.contains("id-swap-status-error")).toBe(false);
  });

  test("clearQuote empties the quote line and no-ops when absent", () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-quote").textContent = "≈ 1 USDC";
    F.clearQuote(panel);
    expect(panel.querySelector(".id-swap-quote").textContent).toBe("");
    expect(() => F.clearQuote(document.createElement("div"))).not.toThrow();
  });

  test("refreshQuote: a no-route result clears the prior quote and marks status red", async () => {
    const panel = mountPanel([]);
    panel.querySelector(".id-swap-quote").textContent =
      "≈ 0.1167 USDC (max ...)"; // stale
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "393537671";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "10000";
    panel.querySelector(".id-swap-form").classList.add("swap-mode-buy");
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "buy",
          amountIn: BigInt(0),
          maximumSent: BigInt(0),
          amountOut: BigInt(1),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "R",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(panel.querySelector(".id-swap-quote").textContent).toBe(""); // stale line gone
    const status = panel.querySelector(".id-swap-status");
    expect(status.textContent).toContain("No route available");
    expect(status.classList.contains("id-swap-status-error")).toBe(true);
    delete window.asastatsSwap;
  });

  test("refreshQuote: a successful quote clears any prior error styling", async () => {
    const panel = mountPanel([]);
    panel
      .querySelector(".id-swap-status")
      .classList.add("id-swap-status-error");
    panel.querySelector(".id-swap-from").value = "0";
    const to = panel.querySelector(".id-swap-to");
    to.value = "31566704";
    to.dataset.decimals = "6";
    panel.querySelector(".id-swap-amount").value = "1";
    window.asastatsSwap = { activeAddress: () => "ADDR" };
    const ctx = {
      fromAddress: "ADDR",
      cfg: {},
      adapter: {
        getQuote: jest.fn(async () => ({
          mode: "sell",
          amountOut: BigInt(2000000),
          amountIn: BigInt(1000000),
          minimumReceived: BigInt(1990000),
          priceImpactPct: 0,
          feesTotal: 0,
          routeLabel: "pact",
        })),
      },
    };
    await F.refreshQuote(panel, ctx);
    expect(
      panel
        .querySelector(".id-swap-status")
        .classList.contains("id-swap-status-error"),
    ).toBe(false);
    delete window.asastatsSwap;
  });
});
