/**
 * @jest-environment jsdom
 */

const fs = require("fs");
const path = require("path");
const html = fs.readFileSync(path.resolve(__dirname, "./index.html"), "utf8");
const jquery = require("../../static/historic/jquery-2.2.4.min.js");

window.$ = jquery;

// Mock external plugins and globals
$.prototype.tabs = jest.fn();
$.prototype.collapsible = jest.fn();
$.prototype.modal = jest.fn();
$.prototype.tooltip = jest.fn();
window.mainConsolidated = jest.fn();
window.scrollToView = jest.fn(() => true);
window.htmx = { trigger: jest.fn() };
window.setTotalCharts = jest.fn();
window.setTotalNoNft = jest.fn();
window.M = {
  Modal: {
    getInstance: jest.fn(() => ({ open: jest.fn() })),
  },
};
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn().mockImplementation(() => Promise.resolve()),
  },
});

const historic = require("../../static/historic/historic.js");
const { getEvents } = require("./test_helpers");

jest.dontMock("fs");

beforeEach(() => {
  document.documentElement.innerHTML = html.toString();
  jest.clearAllMocks();
  localStorage.clear();

  // Provide Chart.js mock for all chart tests
  global.Chart = jest.fn().mockImplementation((ctx, config) => {
    const chartInstance = {
      ctx,
      config,
      data: config.data || { datasets: [{ data: [] }] },
      options: config.options || {
        scales: {
          x: { min: 0, max: 100, getValueForPixel: jest.fn(() => 50) },
        },
        plugins: { zoom: { zoom: { wheel: {}, pinch: {} }, pan: {} } },
      },
      update: jest.fn(),
      resetZoom: jest.fn(),
      resize: jest.fn(),
      scales: { x: { min: 10, max: 90, getValueForPixel: jest.fn(() => 50) } },
    };

    // Simulate zoom completion triggering during update
    chartInstance.update = jest.fn(() => {
      if (
        chartInstance.options.plugins &&
        chartInstance.options.plugins.zoom.zoom.onZoomComplete
      ) {
        chartInstance.options.plugins.zoom.zoom.onZoomComplete({
          chart: chartInstance,
        });
      }
      if (
        chartInstance.options.plugins &&
        chartInstance.options.plugins.zoom.pan.onPanComplete
      ) {
        chartInstance.options.plugins.zoom.pan.onPanComplete({
          chart: chartInstance,
        });
      }
    });

    // Attach chart to canvas for later reference in tests
    ctx.canvas.chart = chartInstance;

    return chartInstance;
  });
});

afterEach(() => {
  jest.resetModules();
  jest.clearAllTimers();
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Initialization & Reset
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: Initialization", function () {
  it("initHistoric exists and can run", () => {
    expect(historic.initHistoric).toBeDefined();
    expect(() => historic.initHistoric()).not.toThrow();
  });

  it("mainHistoric binds events and initializes components", function () {
    historic.mainHistoric();
    const events = global.getEvents
      ? global.getEvents($("body")[0])
      : $._data($("body")[0], "events");
    expect(events["htmx:wsAfterMessage"][0].handler.name).toBe(
      "messageReceived",
    );
    expect($.prototype.tabs).toHaveBeenCalled();
    expect($.prototype.collapsible).toHaveBeenCalled();
    expect($.prototype.modal).toHaveBeenCalled();
  });

  it("resetHistoric rebinds events and runs view setup", function () {
    document.body.innerHTML += '<div id="id-assets" data-label="ALGO"></div>';
    window.mainConsolidated.mockClear();
    historic.resetHistoric();
    expect($.prototype.tooltip).toHaveBeenCalled();
    expect(window.mainConsolidated).toHaveBeenCalled();
  });
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Websocket communication
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: Websocket communication", () => {
  it("handles update_charts message", () => {
    historic.messageReceived({
      detail: {
        message: JSON.stringify({
          type: "update_charts",
          data: { bars: {}, candles: {} },
        }),
      },
    });
    expect(global.Chart).toHaveBeenCalledTimes(2);
  });

  it("handles show_update message", () => {
    historic.messageReceived({
      detail: { message: JSON.stringify({ type: "show_update" }) },
    });
    expect($.prototype.tabs).toHaveBeenCalledWith("select", "tupdate");
  });

  it("handles lock_interaction message", () => {
    // Ensure hidden inputs exist so submitView doesn't crash
    document.body.innerHTML += `
    <input id="view-x-min" />
    <input id="view-x-max" />
  `;
    // Create fresh charts → setUILockedBlur can access them
    historic.populateBarsChart({ data: { datasets: [] }, xmin: 0, xmax: 100 });
    historic.populateCandlesChart({
      data: { datasets: [] },
      xmin: 0,
      xmax: 100,
    });
    // Lock and verify blur
    historic.setUILockedBlur(true);
    expect(
      document.getElementById("id-bars").classList.contains("chart-blurred"),
    ).toBeTruthy();
    // Unlock when active tab is not #tcandles → showBars called
    $('a[href="#tbars"]').addClass("active");
    historic.setUILockedBlur(false);
    expect(
      document.getElementById("id-bars").classList.contains("chart-blurred"),
    ).toBeFalsy();
    expect($.prototype.tabs).toHaveBeenCalledWith("select", "tbars");
  });

  it("handles lock_no_blur message", () => {
    historic.messageReceived({
      detail: {
        message: JSON.stringify({ type: "lock_no_blur", locked: true }),
      },
    });
    expect($("body").css("cursor")).toBe("progress");
  });

  it("falls back to resetHistoric on raw HTML (JSON parse error)", () => {
    window.mainConsolidated.mockClear();
    historic.messageReceived({ detail: { message: "<div>Bad JSON</div>" } });
    expect(window.mainConsolidated).toHaveBeenCalled(); // mainConsolidated is called inside resetHistoric
  });
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: HTMX Submitters
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: HTMX Submitters", () => {
  beforeEach(() => {
    document.body.innerHTML += `
      <input id="show-x-val" /><input id="show-label" />
      <input id="view-x-min" /><input id="view-x-max" />
    `;
  });

  it("submitShow updates inputs and triggers htmx", () => {
    historic.submitShow(100, "ALGO");
    expect(document.getElementById("show-x-val").value).toBe("100");
    expect(document.getElementById("show-label").value).toBe("ALGO");
    expect(window.htmx.trigger).toHaveBeenCalledWith("#id-show", "submit");
  });

  it("submitView updates inputs and triggers htmx", () => {
    historic.submitView(10, 50);
    expect(document.getElementById("view-x-min").value).toBe("10");
    expect(document.getElementById("view-x-max").value).toBe("50");
    expect(window.htmx.trigger).toHaveBeenCalledWith("#id-view", "submit");
  });
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Charts helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: Charts helper functions", () => {
  beforeEach(() => {
    document.body.innerHTML += `
      <input id="show-x-val" /><input id="show-label" />
      <input id="view-x-min" /><input id="view-x-max" />
    `;
  });

  it("handleCandleClick triggers submitShow with correct timestamp based on modifiers", () => {
    const chart = {
      data: {
        datasets: [{ data: [{ x: 10, ot: 11, ct: 22, ht: 33, lt: 44 }] }],
      },
    };
    historic.handleCandleClick({ ctrlKey: true }, 10, chart, 0);
    expect(document.getElementById("show-x-val").value).toBe("11");
    historic.handleCandleClick({ ctrlKey: true }, 10, chart, 1);
    expect(document.getElementById("show-x-val").value).toBe("22");
    historic.handleCandleClick({ ctrlKey: false }, 10, chart, 1);
    expect(document.getElementById("show-x-val").value).toBe("33");
    historic.handleCandleClick({ ctrlKey: false }, 10, chart, 0);
    expect(document.getElementById("show-x-val").value).toBe("44");
  });

  it("barChartClicked handles intersection events", () => {
    document.body.innerHTML +=
      '<div class="active"><div><div class="unit">ALGO</div></div></div>';
    // First trigger will hit submitShow because `shownTime != selectedIdx` (undefined != 5)
    const evtShow = {
      chart: {
        getElementsAtEventForMode: () => [{ index: 5, datasetIndex: 0 }],
        data: { datasets: [{ label: "ALGO" }] },
      },
    };
    historic.barChartClicked(evtShow);
    expect(window.htmx.trigger).toHaveBeenCalledWith("#id-show", "submit");
    // Second trigger bypasses `submitShow` by making `selectedIdx` undefined
    // (`undefined != undefined` is false), thus calling `scrollToUnit`
    const evtScroll = {
      chart: {
        getElementsAtEventForMode: () => [
          { index: undefined, datasetIndex: 0 },
        ],
        data: { datasets: [{ label: "ALGO" }] },
      },
    };
    historic.barChartClicked(evtScroll);
    expect(window.scrollToView).toHaveBeenCalled();
  });

  it("viewChanged triggers submitView with scale limits unless suppressed", () => {
    const evt = { chart: { scales: { x: { min: 5, max: 95 } } } };
    historic.viewChanged(evt);
    expect(window.htmx.trigger).toHaveBeenCalledWith("#id-view", "submit");
    // Test zoom suppression coverage during chart update
    window.htmx.trigger.mockClear();
    historic.populateCharts({ bars: { data: {} }, candles: { data: {} } });
    // Re-populate hits the update block which enables `suppressZoom=true` during the update
    historic.populateCharts({ bars: { data: {} }, candles: { data: {} } });
    expect(window.htmx.trigger).not.toHaveBeenCalled(); // The mock update fires zoom events while suppressed
  });

  it("populates and binds canvas touch/mouse events for candles", () => {
    jest.useFakeTimers();
    document.body.innerHTML += '<canvas id="id-candles"></canvas>';
    historic.populateCandlesChart({
      data: { datasets: [{ data: [{ x: 50, ot: 1, ct: 2, ht: 3, lt: 4 }] }] },
      xmin: 0,
      xmax: 100,
    });
    const canvas = document.getElementById("id-candles");
    canvas.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
    });
    // Test mouse down
    canvas.dispatchEvent(new MouseEvent("mousedown", { button: 0 }));
    expect(document.getElementById("show-x-val").value).toBe("4"); // lt (button 0, no ctrl)
    // Test touch start (long press timeout)
    const touchStartEvt = new Event("touchstart");
    touchStartEvt.touches = [{ clientX: 50 }];
    canvas.dispatchEvent(touchStartEvt);
    jest.advanceTimersByTime(650);
    expect(document.getElementById("show-x-val").value).toBe("3"); // ht (button 1 forced in touch handler)
    // Test touch start with >1 touch (should return early)
    const touchStartMultiple = new Event("touchstart");
    touchStartMultiple.touches = [{ clientX: 50 }, { clientX: 60 }];
    canvas.dispatchEvent(touchStartMultiple);
    // Test touch cancelations
    canvas.dispatchEvent(new Event("touchmove"));
    canvas.dispatchEvent(new Event("touchend"));
    jest.useRealTimers();
  });

  it("updateChart correctly updates state", () => {
    const mockChartInstance = {
      data: {},
      options: { scales: { x: {} } },
      update: jest.fn(),
      resetZoom: jest.fn(),
    };
    historic.updateChart(mockChartInstance, {
      data: { labels: ["a"] },
      xmin: 0,
      xmax: 10,
    });
    expect(mockChartInstance.data.labels[0]).toBe("a");
    expect(mockChartInstance.update).toHaveBeenCalled();
    expect(mockChartInstance.resetZoom).toHaveBeenCalled();
  });

  it("onHover changes cursor style", () => {
    historic.populateBarsChart({ data: { datasets: [] }, xmin: 0, xmax: 100 });
    historic.populateCandlesChart({
      data: { datasets: [] },
      xmin: 0,
      xmax: 100,
    });
    const mockEvent = { native: { target: { style: {} } } };
    // bars chart
    const barsChart = document.getElementById("id-bars").chart;
    barsChart.options.onHover(mockEvent, []);
    expect(mockEvent.native.target.style.cursor).toBe("default");
    barsChart.options.onHover(mockEvent, [{}]);
    expect(mockEvent.native.target.style.cursor).toBe("pointer");
    // candles chart
    const candlesChart = document.getElementById("id-candles").chart;
    candlesChart.options.onHover(mockEvent, []);
    expect(mockEvent.native.target.style.cursor).toBe("default");
    candlesChart.options.onHover(mockEvent, [{}]);
    expect(mockEvent.native.target.style.cursor).toBe("pointer");
  });
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Currency functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: Currency functions", () => {
  it("formats currency correctly", () => {
    expect(historic.cur(1234.567)).toBe("1,234.57");
    expect(historic.dec6(1234.5678912)).toBe("1,234.567891");
  });

  it("setCurrency returns false if element missing", () => {
    document.body.innerHTML = "";
    expect(historic.setCurrency("USD")).toBe(false);
  });

  it("setCurrency manipulates DOM based on USD/ALGO", () => {
    document.body.innerHTML = `
      <div class="pricetip" data-price="0.25" data-pricealgo="4.0" data-total="100"></div>
      <span class="val cons-value" data-val="100"></span>
      <span class="val" data-val="50"></span>
      <div class="switch"><input type="checkbox"></div>
    `;
    historic.setCurrency("USD");
    expect($(".pricetip")[0].innerHTML).toBe("100.00 USD");
    expect($(".switch input").prop("checked")).toBe(true);
    expect($("span.val")[1].dataset.position).toBe("right");
    historic.setCurrency("ALGO");
    expect($(".pricetip")[0].innerHTML).toBe("25.00 ALGO");
    expect($(".switch input").prop("checked")).toBe(false);
  });

  it("toggleCurrency flips state and sets localStorage", () => {
    document.body.innerHTML =
      '<div class="switch"><input type="checkbox" checked></div>';
    const checkbox = $(".switch input")[0];
    historic.toggleCurrency.call(checkbox);
    expect(localStorage.getItem("hcur")).toBe("USD");
  });
});

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("SECTION: Helper functions", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  it("copyToClipboard copies prev element text", () => {
    document.body.innerHTML =
      '<span>TextToCopy</span><button class="copy"></button>';
    const btn = $(".copy")[0];
    historic.copyToClipboard.call(btn);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("TextToCopy");
    jest.runAllTimers();
    expect($("span").css("color")).not.toBe("#ababab");
  });

  it("deferImages updates src, skips empty, and handles fallback", () => {
    document.body.innerHTML = `
      <img class="nft" data-src="real.jpg" src="placeholder.jpg" />
      <img class="nft" src="placeholder.jpg" />
    `;
    const images = document.getElementsByClassName("nft");
    historic.deferImages(images);
    expect(images[0].getAttribute("src")).toBe("real.jpg");
    expect(images[1].getAttribute("src")).toBe("placeholder.jpg"); // Untouched
    // Trigger error fallback
    images[0].onerror();
    expect(images[0].src).toContain("nft.png");
  });

  it("isItemInArray correctly checks array membership", () => {
    expect(historic.isItemInArray(undefined, [])).toBe(true);
    expect(historic.isItemInArray(1, [1, 2, 3])).toBe(true);
    expect(historic.isItemInArray(5, [1, 2, 3])).toBe(false);
  });

  it("filterChange toggles visibility and handles comma split", () => {
    document.body.innerHTML = `
      <input id="filter" value="ALGO great" />   <!-- both words match the text -->
      <div class="collapsible">
        <div id="item1" class="fitem"><span>ALGO is great</span></div>
      </div>
    `;
    $("#item1").hide();
    // Valid key (13 = enter)
    historic.filterChange({ keyCode: 13 });
    expect(document.getElementById("item1").style.display).not.toBe("none");
    // Invalid key
    $("#item1").hide();
    historic.filterChange({ keyCode: 999 });
    expect(document.getElementById("item1").style.display).toBe("none");
  });

  it("filterChange handles empty filter (resets visibility)", () => {
    document.body.innerHTML =
      '<input id="filter" value="" /><div class="fitem" style="display:none;"></div>';
    historic.filterChange({ keyCode: 13 });
    expect(document.querySelector(".fitem").style.display).not.toBe("none");
  });

  it("showMatchedNodes unhides intersecting nodes and returns false if none", () => {
    document.body.innerHTML = `
      <div class="collapsible">
        <div class="fitem"><div id="match1" style="display:none"></div></div>
        <div class="fitem"><div id="match2" style="display:none"></div></div>
      </div>
    `;
    // Multiple matches intersection
    historic.showMatchedNodes([["match1", "match2"], ["match1"]]);
    expect(document.getElementById("match1").style.display).not.toBe("none");
    expect(document.getElementById("match2").style.display).toBe("none");
    // Empty matches
    expect(historic.showMatchedNodes([])).toBe(false);
  });

  it("showMatchedNodes reveals nfticon with matching id", () => {
    document.body.innerHTML = `
    <div class="collapsible">
      <div id="match1" class="fitem" style="display:none;"></div>
      <div class="nfticon" id="tmatch1" style="display:none;"></div>
    </div>
  `;
    historic.showMatchedNodes([["match1"], ["match1"]]);
    expect(document.getElementById("match1").style.display).not.toBe("none");
    expect(document.getElementById("tmatch1").style.display).not.toBe("none");
  });

  it("scrollToUnit handles normal, NFT, LOFTY, and unknown units", () => {
    document.body.innerHTML = `
      <div id="id-nft"></div>
      <div class="active"><div><div class="unit">LOFTY-123</div></div></div>
      <div class="active"><div><div class="unit">ALGO</div></div></div>
    `;
    historic.scrollToUnit("NFT");
    expect(window.scrollToView).toHaveBeenCalled();
    historic.scrollToUnit("LOFTY");
    expect(window.scrollToView).toHaveBeenCalled();
    historic.scrollToUnit("ALGO");
    expect(window.scrollToView).toHaveBeenCalled();
    // Unknown unit does not crash
    expect(() => historic.scrollToUnit("UNKNOWN")).not.toThrow();
    // unmoved delay path
    window.scrollToView.mockReturnValueOnce(true);
    historic.scrollToUnit("ALGO");
    jest.runAllTimers();
  });

  it("tabShow runs without crashing if charts are missing", () => {
    expect(() => historic.tabShow({ id: "tbars" })).not.toThrow();
    expect(() => historic.tabShow({ id: "tcandles" })).not.toThrow();
  });

  it("tabShow resizes existing charts", () => {
    // Force fresh creation so canvas.chart is attached by the mock
    historic.populateBarsChart({ data: { datasets: [] }, xmin: 0, xmax: 100 });
    historic.populateCandlesChart({
      data: { datasets: [] },
      xmin: 0,
      xmax: 100,
    });
    // Bars tab
    historic.tabShow({ id: "tbars" });
    const barsCanvas = document.getElementById("id-bars");
    expect(barsCanvas.chart.resize).toHaveBeenCalled();
    // Candles tab
    historic.tabShow({ id: "tcandles" });
    const candlesCanvas = document.getElementById("id-candles");
    expect(candlesCanvas.chart.resize).toHaveBeenCalled();
  });

  it("toggleTotalNoNft sets state and calls generic function", () => {
    document.body.innerHTML =
      '<div class="totalnonft"><input type="checkbox" checked></div>';
    historic.toggleTotalNoNft.call($(".totalnonft input")[0]);
    expect(localStorage.getItem("htotalnonft")).toBe("y");
    expect(window.setTotalNoNft).toHaveBeenCalledWith("y");
  });

  it("openModalConfirmReset and resetData handle form resets", () => {
    document.body.innerHTML = `
      <button id="id-reset"></button>
      <button id="id_confirm"></button>
      <p id="id_pconfirm"></p>
      <div id="id_modalconfirm"></div>
      <form id="id-reset-form"></form>
    `;
    // Bind main events manually for testing
    historic.mainHistoric();
    // Mock the form submit function
    document.getElementById("id-reset").submit = jest.fn();
    // trigger resets
    $("#id-reset").trigger("click");
    expect(window.M.Modal.getInstance).toHaveBeenCalled();
    $("#id_confirm").trigger("click");
    expect(document.getElementById("id-reset").submit).toHaveBeenCalled();
  });
});
