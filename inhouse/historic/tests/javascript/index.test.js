const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.resolve(__dirname, './index.html'), 'utf8');
const jquery = require('../../static/historic/jquery-2.2.4.min.js');

window.$ = jquery;

$.prototype.tabs = jest.fn();
$.prototype.collapsible = jest.fn();
$.prototype.modal = jest.fn();
$.prototype.tooltip = jest.fn();
window.mainConsolidated = jest.fn();
window.scrollToView = jest.fn();

const materialize = require('../../static/historic/materialize.min.js');
const chartjs = require('../../static/historic/chart.min.js');
const historic = require('../../static/historic/historic.js');

jest
  .dontMock('fs');

beforeEach(() => {
  document.documentElement.innerHTML = html.toString();
  historic.mainHistoric();
});

afterEach(() => {
  jest.resetModules();
});


/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Initialization
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("in SECTION: Initialization", function () {

  // mainHistoric
  describe("mainHistoric function", function () {

    it('binds wsAfterMessage on body', function () {
      $("body").off("htmx:wsAfterMessage");
      historic.mainHistoric();
      var events = getEvents($("body")[0]);
      expect(events).not.toBe(undefined);
      expect(events["htmx:wsAfterMessage"][0].handler.name).toBe("messageReceived");
    });

    it('initializes tabs', function () {
      const spyFunc = jest.spyOn($.prototype, "tabs");
      spyFunc.mockClear();
      historic.mainHistoric();
      expect(spyFunc).toHaveBeenCalledWith({ onShow: historic.tabShow });
    });

  });

});


/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
describe("in SECTION: Helper functions", function () {

  // messageReceived
  // populateBarsChart
  // populateCandlesChart
  // populateCharts
  // tabShow

});


/**
 * @jest-environment jsdom
 */

const {
  messageReceived,
  populateBarsChart,
  populateCandlesChart,
  populateCharts,
  tabShow,
} = require('../../static/historic/historic.js');

const { mockChart, resetDom } = require('./test_helpers');

describe('Historic Chart Functions', () => {
  let canvasBars, canvasCandles;

  beforeEach(() => {
    resetDom(); // Clear and prepare DOM
    canvasBars = document.createElement('canvas');
    canvasBars.id = 'id-bars';
    document.body.appendChild(canvasBars);

    canvasCandles = document.createElement('canvas');
    canvasCandles.id = 'id-candles';
    document.body.appendChild(canvasCandles);

    // Provide a robust mock that won't crash when historic.js tries to mutate deep properties
    global.Chart = jest.fn().mockImplementation(() => ({
      data: {},
      options: {
        scales: { x: {} },
        plugins: { zoom: { zoom: { wheel: {}, pinch: {} }, pan: {} } }
      },
      update: jest.fn(),
      resetZoom: jest.fn(),
      resize: jest.fn(),
    }));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('messageReceived', () => {
    it('should call populateCharts when valid update_charts message is received', () => {
      const data = { bars: { data: {} }, candles: { data: {} } };
      const event = {
        detail: { message: JSON.stringify({ type: 'update_charts', data }) },
      };

      global.Chart.mockClear();
      messageReceived(event);

      // Verify the side effect: Chart constructor was called twice
      expect(global.Chart).toHaveBeenCalledTimes(2);
    });

    it('should not throw error on malformed JSON', () => {
      const event = { detail: { message: "<div>HTML string</div>" } };
      expect(() => messageReceived(event)).not.toThrow();
    });
  });

  describe('populateBarsChart', () => {
    it('should initialize a bar chart on the bars canvas', () => {
      const data = { data: { labels: [], datasets: [] }, xmin: 0, xmax: 10 };
      populateBarsChart(data);
      expect(global.Chart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
        type: 'bar',
        data: data.data, // Match what historic.js actually passes to Chart
      }));
    });
  });

  describe('populateCandlesChart', () => {
    it('should initialize a candlestick chart on the candles canvas', () => {
      const data = { data: { datasets: [] }, xmin: 0, xmax: 10 };
      populateCandlesChart(data);
      expect(global.Chart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
        type: 'candlestick',
        data: data.data, // Match what historic.js actually passes to Chart
      }));
    });
  });

  describe('populateCharts', () => {
    it('should update existing charts if they are defined', () => {
      // Initialize module state first so it takes the "update" path
      populateBarsChart({ data: {} });
      populateCandlesChart({ data: {} });

      const mockBars = global.Chart.mock.results[0].value;
      const mockCandles = global.Chart.mock.results[1].value;

      const data = {
        bars: { data: { label: 'bars' }, xmin: 0, xmax: 10 },
        candles: { data: { label: 'candles' }, xmin: 0, xmax: 10 }
      };

      populateCharts(data);

      expect(mockBars.data).toEqual(data.bars.data);
      expect(mockBars.update).toHaveBeenCalled();
    });

    it('should create new charts if none exist', () => {
      // Re-require a fresh instance of the module so internal variables are undefined
      jest.resetModules();
      const freshHistoric = require('../../static/historic/historic.js');
      global.Chart.mockClear();

      const data = { bars: { data: {} }, candles: { data: {} } };
      freshHistoric.populateCharts(data);

      expect(global.Chart).toHaveBeenCalledTimes(2);
    });
  });

  describe('tabShow', () => {
    it('should resize bars chart when Bars tab is shown', () => {
      // Populate first so the module sets its internal chartBars variable
      populateBarsChart({ data: {} });
      const mockBars = global.Chart.mock.results[global.Chart.mock.results.length - 1].value;

      tabShow({ id: 'tbars' });
      expect(mockBars.resize).toHaveBeenCalled();
    });

    it('should resize candles chart when Candles tab is shown', () => {
      populateCandlesChart({ data: {} });
      const mockCandles = global.Chart.mock.results[global.Chart.mock.results.length - 1].value;

      tabShow({ id: 'tcandles' });
      expect(mockCandles.resize).toHaveBeenCalled();
    });

    it('should do nothing if unrelated tab is shown', () => {
      // 1. Populate the charts so they exist in the module's state AND in the mock results
      populateBarsChart({ data: {} });
      populateCandlesChart({ data: {} });

      // 2. Now we can safely grab the mocked chart instances
      const mockBars = global.Chart.mock.results[0].value;
      const mockCandles = global.Chart.mock.results[1].value;

      // 3. Clear their specific resize mocks just to be safe
      mockBars.resize.mockClear();
      mockCandles.resize.mockClear();

      // 4. Trigger the unrelated tab
      tabShow({ id: 'tsettings' });

      // 5. Verify resize was NOT called
      expect(mockBars.resize).not.toHaveBeenCalled();
      expect(mockCandles.resize).not.toHaveBeenCalled();
    });

  });

});

