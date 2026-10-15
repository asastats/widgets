/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

global.getEvents = (element) => {
  var elemEvents = $._data(element, "events");
  var allDocEvnts = $._data(document, "events");
  for (var evntType in allDocEvnts) {
    if (allDocEvnts.hasOwnProperty(evntType)) {
      var evts = allDocEvnts[evntType];
      for (var i = 0; i < evts.length; i++) {
        if ($(element).is(evts[i].selector)) {
          if (elemEvents == null) {
            elemEvents = {};
          }
          if (!elemEvents.hasOwnProperty(evntType)) {
            elemEvents[evntType] = [];
          }
          elemEvents[evntType].push(evts[i]);
        }
      }
    }
  }
  return elemEvents;
}

function mockChart() {
  return {
    data: {},
    options: {
      scales: {
        x: {}
      }
    },
    update: jest.fn(),
    resetZoom: jest.fn(),
    resize: jest.fn(),
  };
}

function resetDom() {
  document.body.innerHTML = '';
  delete global.chartBars;
  delete global.chartCandles;
}

module.exports = {
  mockChart,
  resetDom,
};



/**
 * A stand-in for the host's `Fiat` (the website's static/js/fiat.js) with the
 * calls the widgets make. Not the host's file: this repository is tested alone.
 */
global.fiatStub = (code = "USD", rate = 1, symbol = code === "USD" ? "$" : "") => ({
  code: () => code,
  rate: () => rate,
  fromUsd: (usd) => usd * rate,
  symbol: () => symbol,
  isFiatSide: (stored) => !!stored && stored !== "ALGO",
});

// The host page loads its fiat.js before the widget; a reader who chose nothing is USD.
global.Fiat = global.fiatStub();
