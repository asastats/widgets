const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.resolve(__dirname, './index.html'), 'utf8');
const jquery = require('../../static/historic/jquery-2.2.4.min.js');

window.$ = jquery;

$.prototype.tabs = jest.fn();

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

    global.Chart = jest.fn().mockImplementation(() => mockChart());
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('messageReceived', () => {
    it('should call populateCharts when valid update_charts message is received', () => {
      const data = { bars: {}, candles: {} };
      const spy = jest.spyOn(require('../../static/historic/historic.js'), 'populateCharts');

      const event = {
        detail: {
          message: JSON.stringify({
            type: 'update_charts',
            data,
          }),
        },
      };

      messageReceived(event);
      expect(spy).toHaveBeenCalledWith(data);
      spy.mockRestore();
    });

    it('should not throw error on malformed JSON', () => {
      const event = {
        detail: { message: "<div>HTML string</div>" },
      };
      expect(() => messageReceived(event)).not.toThrow();
    });
  });

  describe('populateBarsChart', () => {
    it('should initialize a bar chart on the bars canvas', () => {
      const data = { labels: [], datasets: [] };
      populateBarsChart(data);
      expect(global.Chart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
        type: 'bar',
        data,
      }));
    });
  });

  describe('populateCandlesChart', () => {
    it('should initialize a candlestick chart on the candles canvas', () => {
      const data = { datasets: [] };
      populateCandlesChart(data);
      expect(global.Chart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
        type: 'candlestick',
        data,
      }));
    });
  });

  describe('populateCharts', () => {
    it('should update existing charts if they are defined', () => {
      const mockBars = mockChart();
      const mockCandles = mockChart();
      global.chartBars = mockBars;
      global.chartCandles = mockCandles;

      const data = { bars: { label: 'bars' }, candles: { label: 'candles' } };

      populateCharts(data);

      expect(mockBars.data).toEqual(data.bars);
      expect(mockBars.update).toHaveBeenCalled();
      expect(mockCandles.data).toEqual(data.candles);
      expect(mockCandles.update).toHaveBeenCalled();
    });

    it('should create new charts if none exist', () => {
      global.chartBars = undefined;
      global.chartCandles = undefined;

      const data = { bars: { datasets: [] }, candles: { datasets: [] } };

      populateCharts(data);

      expect(global.Chart).toHaveBeenCalledTimes(2);
    });
  });

  describe('tabShow', () => {
    it('should resize bars chart when Bars tab is shown', () => {
      const mockBars = mockChart();
      global.chartBars = mockBars;

      tabShow({ id: 'tbars' });

      expect(mockBars.resize).toHaveBeenCalled();
    });

    it('should resize candles chart when Candles tab is shown', () => {
      const mockCandles = mockChart();
      global.chartCandles = mockCandles;

      tabShow({ id: 'tcandles' });

      expect(mockCandles.resize).toHaveBeenCalled();
    });

    it('should do nothing if unrelated tab is shown', () => {
      global.chartBars = mockChart();
      global.chartCandles = mockChart();

      tabShow({ id: 'tsettings' });

      expect(global.chartBars.resize).not.toHaveBeenCalled();
      expect(global.chartCandles.resize).not.toHaveBeenCalled();
    });
  });
});

