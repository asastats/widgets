/**
 * @file www.asastats.com historic data widget browser side functions
 * @author Ivica Paleka
 */

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Initialization
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */
var chartBars;
var chartCandles;
var suppressZoom = false;
var shownTime;
var longPressTimeout = null;

/**
 * Call main function upon finished document loading
 *
 */
$(mainHistoric);

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Initialization
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/**
 * Function called upon page load
 * @function initHistoric
 *
 */
function initHistoric() { }

/**
 * Assign window onload method to initIndex function.
 * That function will be triggered after all the page content has been already loaded.
 *
 */
window.onload = initHistoric;

/**
 * Main function of the historic data widget
 * @function mainHistoric
 *
 */
function mainHistoric() {
  $(".indeterminate").parent().addClass("progress");
  $(".collapsible").collapsible();
  $(".modal").modal();
  $(".tabs").tabs({ onShow: tabShow });
  $("body").on("htmx:wsAfterMessage", messageReceived);
  $(".switch").find("input[type=checkbox]").on("change", toggleCurrency);
  $(".totalnonft").find("input[type=checkbox]").on("change", toggleTotalNoNft);
  $("#id-reset").on("click", openModalConfirmReset);
  $("#id_confirm").on("click", resetData);
}

/**
 * Bound events and process initial data
 * @function resetHistoric
 *
 */
function resetHistoric() {
  $(".collapsible").collapsible();
  $(".pricetip").tooltip();
  $(".val").tooltip({ enterDelay: 800 });
  $(".switch").find("input[type=checkbox]").on("change", toggleCurrency);
  $(".totalnonft").find("input[type=checkbox]").on("change", toggleTotalNoNft);
  $("#filter").on("keypress", filterChange);
  $(".copy").on("click", copyToClipboard);
  mainConsolidated();
  setCurrency(localStorage.getItem("hcur") || "ALGO");
  deferImages(document.getElementsByClassName("nft"));
  var label = $("#id-assets").data("label");
  scrollToUnit(label);
}

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Websocket communication
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/**
 * Parse message received through websocket
 * @function messageReceived
 *
 * @param {object} event htmx:wsAfterMessage event object
 *
 */
function messageReceived(event) {
  var rawMessage = event.detail.message;

  try {
    var message = JSON.parse(rawMessage);
    if (message.type === "update_charts" && message.data) {
      populateCharts(message.data);
    } else if (message.type === "show_update") {
      showUpdate();
    } else if (message.type === "lock_interaction") {
      setUILockedBlur(message.locked);
    } else if (message.type === "lock_no_blur") {
      setUILocked(message.locked);
    }
  } catch (e) {
    // raw HTML is received
    resetHistoric();
  }
}

/**
 * Send x-axis value and label to fetch data for
 * @function submitShow
 *
 * @param {Number} xVal chart's x-axis value
 * @param {Number} label label to reveal
 *
 */
function submitShow(xVal, label) {
  document.getElementById("show-x-val").value = xVal;
  document.getElementById("show-label").value = label;

  htmx.trigger("#id-show", "submit");
}

/**
 * Send minimum and maximum x-axis values message to the consumer using htmx
 * @function submitView
 *
 * @param {Number} xMin chart's minimum x-axis value
 * @param {Number} xMax chart's maximum x-axis value
 *
 */
function submitView(xMin, xMax) {
  document.getElementById("view-x-min").value = xMin;
  document.getElementById("view-x-max").value = xMax;

  htmx.trigger("#id-view", "submit");
}

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Charts helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/**
 * Expand selected asset's data or send message to the consumer to fetch timestamp data
 * @function barChartClicked
 *
 * @param {object} evt click event object
 * @param {object} elements chart's elements collection
 *
 */
function barChartClicked(evt, elements) {
  var points = evt.chart.getElementsAtEventForMode(
    evt,
    "nearest",
    { intersect: true },
    true,
  );
  if (points.length) {
    var firstPoint = points[0];
    var selectedIdx = firstPoint.index;
    var datasetIndex = firstPoint.datasetIndex;
    var label = evt.chart.data.datasets[datasetIndex].label;

    console.log("Clicked dataset label:", label);
    console.log("Data index:", selectedIdx);
    if (shownTime != selectedIdx) {
      return submitShow(selectedIdx, label);
    }

    scrollToUnit(label);
  }
}

/**
 * Return candle from dataset ccollectio nwhich is the nearestr to provided x point.
 * @function findNearest
 *
 * @param {Array.<object>} dataset candles collection
 * @param {Number} xValue pont on x-axis
 *
 */
function findNearest(dataset, xValue) {
  var nearest = null;
  var minDiff = Infinity;

  for (var i = 0; i < dataset.length; i++) {
    var candle = dataset[i];
    var candleX = candle.x;
    var diff = Math.abs(candleX - xValue);
    if (diff < minDiff) {
      minDiff = diff;
      nearest = candle;
    }
  }
  // console.log('Nearest candle:', nearest);
  return nearest;
}

/**
 * Send message to the consumer to fetch timestamp data if a candle is clicked
 * @function handleCandleClick
 *
 * @param {object} evt click event object
 * @param {object} xValue x-axis value of clicked point
 * @param {object} chart candlestick chart instance
 * @param {Number} button mosue button that is pressed
 *
 */
function handleCandleClick(evt, xValue, chart, button) {
  var timestamp;
  // console.log('Clicked x-axis value:', xValue);
  var nearest = findNearest(chart.data.datasets[0].data, xValue);
  // console.log('evt.ctrlKey, button:', evt.ctrlKey, button);
  if (evt.ctrlKey && button === 0) {
    timestamp = nearest.ot;
    console.log("Clicked x-axis value ot:", xValue, timestamp);
  } else if (evt.ctrlKey && button === 1) {
    timestamp = nearest.ct;
    console.log("Clicked x-axis value ct:", xValue, timestamp);
  } else if (button === 1) {
    timestamp = nearest.ht;
    console.log("Clicked x-axis value ht:", xValue, timestamp);
  } else {
    timestamp = nearest.lt;
    console.log("Clicked x-axis value lt:", xValue, timestamp);
  }

  return submitShow(timestamp, null);
  // evt.button === 2 // Right-click
  // evt.button === 0 // Left-click
  // evt.button === 1 // Middle-click

  // evt.ctrlKey    // true if Ctrl is held
  // evt.shiftKey   // true if Shift is held
  // evt.altKey     // true if Alt is held
  // evt.metaKey    // true if ⌘ Command (on Mac) is held
}

/**
 * Prevent or enable charts' zooming and panning
 * @function setUILocked
 *
 * @param {Boolean} locked value indicating chart lock state
 *
 */
function setUILocked(locked) {
  if (locked) {
    $(".indeterminate").parent().addClass("progress");
    $("body").css("cursor", "progress");
    $(".process").hide();
    // $('.reset').hide();
  } else {
    $(".indeterminate").parent().removeClass("progress");
    $("body").css("cursor", "default");
    $(".process").show();
    // $('.reset').show();
  }
  $(".reset").prop("disabled", locked);
  // $('.process').prop('disabled', locked);

  [chartBars, chartCandles].forEach(function (chart) {
    // console.log(chart);
    chart.options.plugins.zoom.zoom.wheel.enabled = !locked;
    chart.options.plugins.zoom.zoom.pinch.enabled = !locked;
    chart.options.plugins.zoom.pan.enabled = !locked;
    chart.update();
  });

  if (!locked && $(".active").attr("href") != "#tcandles") {
    showBars();
  }
}

/**
 * Prevent or enable charts' zooming and panning and blur the charts
 * @function setUILockedBlur
 *
 * @param {Boolean} locked value indicating chart lock state
 *
 */
function setUILockedBlur(locked) {
  var canvas;

  setUILocked(locked);

  ["id-bars", "id-candles"].forEach(function (canvasId) {
    canvas = document.getElementById(canvasId);
    if (locked) {
      canvas.classList.add("chart-blurred");
    } else {
      canvas.classList.remove("chart-blurred");
    }
    // console.log(locked);
    // console.log(canvas.classList);
  });
}

/**
 * Send message to the consumer upon candles chart zoom or pan event
 * @function viewChanged
 *
 * @param {object} evt onZoomComplete/onPanComplete event object
 *
 */
function viewChanged(evt) {
  var xScale;

  if (suppressZoom) {
    return;
  }

  xScale = evt.chart.scales["x"];

  submitView(xScale.min, xScale.max);
}

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Currency functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/**
 * Shows provided number as currency
 *
 * @param {jQuery} num
 *
 */
function cur(num) {
  return parseFloat(num).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Shows provided number as 6 digits decimal
 *
 * @param {jQuery} num
 *
 */
function dec6(num) {
  return parseFloat(num).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}

/**
 * Calculate and set currency values based on provided currency code
 *
 * @param {String} code
 *
 */
function setCurrency(code) {
  var elem = $(".pricetip")[0];
  if (typeof elem === "undefined") return false;

  var price = elem.dataset.price;
  var pricealgo = elem.dataset.pricealgo;
  var total = elem.dataset.total;
  if (code == "USD") {
    $(".pricetip").each(function () {
      this.dataset.tooltip =
        cur(total * price) + " ALGO (" + dec6(price) + " ALGO/USD)";
      this.innerHTML = cur(total) + " USD";
    });
    $("span.val").each(function () {
      this.innerHTML = cur(this.dataset.val / price) + " USD";
      this.dataset.tooltip = cur(this.dataset.val) + " ALGO";
      if ($(this).hasClass("cons-value")) this.dataset.position = "bottom";
      else this.dataset.position = "right";
    });
  } else {
    $(".pricetip").each(function () {
      this.dataset.tooltip =
        cur(total) + " USD (" + dec6(pricealgo) + " USD/ALGO)";
      this.innerHTML = cur(total * price) + " ALGO";
    });
    $("span.val").each(function () {
      this.innerHTML = cur(this.dataset.val) + " ALGO";
      this.dataset.tooltip = cur(this.dataset.val / price) + " USD";
      if ($(this).hasClass("cons-value")) this.dataset.position = "bottom";
      else this.dataset.position = "right";
    });
  }
  setTotalCharts();

  $(".switch")
    .find("input[type=checkbox]")
    .prop("checked", code == "USD");
}

/**
 * Switch amounts from ALGO to USD back and forth
 *
 */
function toggleCurrency() {
  var code = $(this).prop("checked") ? "USD" : "ALGO";
  localStorage.setItem("hcur", code);
  setCurrency(code);
}

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: Helper functions
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/**
 * Copy previous element's text to clipboard
 * @function copyToClipboard
 *
 * @param {jQuery} event Triggered click event object
 *
 */
function copyToClipboard(event) {
  var link = $(this).prev();
  if (navigator.clipboard) {
    var color = link.css("color");
    navigator.clipboard.writeText(link.text());
    link.css("color", "#ababab");
    setTimeout(function () {
      link.css("color", color);
    }, 500);
  }
}

/**
 * Assign src attribute from element's dataset src attribute.
 * This is done after all the page content has been already loaded.
 * @function deferImages
 *
 * @param {Array.<object>} images Array of image elements
 *
 */
function deferImages(images) {
  for (var i = 0; i < images.length; i++) {
    if (images[i].getAttribute("data-src")) {
      images[i].setAttribute("src", images[i].getAttribute("data-src"));
    }
  }
}

/**
 * Change visibility of all accordions based on text entered
 *
 * @param {jQuery} evt
 */
function filterChange(evt) {
  var keys = [13, 32, 44, 108, 188];
  if (keys.indexOf(evt.keyCode) > -1) {
    var filter = $("#filter").val();
    if (filter == "") {
      $(".fitem").show();
      $(".collapsible").not(".consolidated").show();
      $(".nfticon").show();
    } else {
      var matches = [];
      var array = filter.split(" ");
      if (filter.split(",").length > array.length) array = filter.split(",");
      for (var i = 0; i < array.length; i++) {
        matches[i] = getNodesThatContain(array[i]);
      }
      showMatchedNodes(matches);
    }
  }
}

/**
 * Return array of list items that contain provided text
 *
 * @param {String} text
 */
function getNodesThatContain(text) {
  var ids = [];
  // var items = [];
  var textNodes = $(".fitem")
    .find(":not(iframe, script, style)")
    .contents()
    .filter(function () {
      return (
        this.nodeType == 3 &&
        this.textContent.toLowerCase().indexOf(text.toLowerCase()) > -1
      );
    });

  textNodes.parent().each(function (index) {
    var item = $(this).parents(".fitem");
    if (!isItemInArray(item.attr("id"), ids)) {
      ids.push(item.attr("id"));
      // items.push(item);
    }
  });
  // return items;
  return ids;
}

/**
 * Return true if provided item is inside output array
 *
 * @param {Number} item
 * @param {Array.Number} array
 */
function isItemInArray(item, array) {
  if (typeof item === "undefined") return true;

  for (var i = 0; i < array.length; i++) {
    if (array[i] === item) {
      return true;
    }
  }
  return false;
}

/**
 * Open modal dialog for user to confirm data reset.
 * @function openModalConfirmReset
 *
 * @param {Object} Triggered event
 *
 */
function openModalConfirmReset(event) {
  event.preventDefault();
  $("#id_pconfirm").text(
    "Are you sure you want to delete all the existing data?",
  );
  var modal = document.querySelector("#id_modalconfirm");
  var instance = M.Modal.getInstance(modal);
  instance.open();
}

/**
 * User has confirmed reset through the confirmation dialog.
 * @function resetData
 *
 * @param {jQuery} event Triggered event object
 *
 */
function resetData(event) {
  $("button[name='reset']").off("click");
  // $("button[name='reset']").trigger("click");
  document.getElementById("id-reset").submit();
}

/**
 * Create bars chart using retrieved data (labels and datasets) and scale boundaries
 * @function populateBarsChart
 *
 * @param {object} chartData bar chart's data and scale boundaries
 *
 */
function populateBarsChart(chartData) {
  var canvasBars = document.getElementById("id-bars");
  var ctxBars = canvasBars.getContext("2d");

  chartBars = new Chart(ctxBars, {
    type: "bar",
    data: chartData.data,
    options: {
      indexAxis: "x",
      responsive: true,
      animation: {
        duration: 300,
      },
      scales: {
        x: {
          stacked: true,
          min: chartData.xmin,
          max: chartData.xmax,
        },
        y: {
          stacked: true,
          ticks: {
            autoSkip: false,
          },
        },
      },
      plugins: {
        legend: {
          position: "top",
        },
        zoom: {
          pan: {
            enabled: true,
            mode: "x",
            modifierKey: "ctrl",
            scaleMode: "x",
            onPanComplete: viewChanged,
          },
          limits: {
            // axis limits
          },
          zoom: {
            wheel: {
              enabled: true,
              modifierKey: "ctrl",
              speed: 0.3,
            },
            pinch: {
              enabled: true,
            },
            mode: "x",
            scaleMode: "x",
            onZoomComplete: viewChanged,
          },
        },
      },
      interaction: {
        mode: "nearest",
        intersect: true,
      },
      onHover: function (evt, elem) {
        evt.native.target.style.cursor = elem[0] ? "pointer" : "default";
      },
      onClick: barChartClicked,
    },
  });
}

/**
 * Create candlestick chart using retrieved data (labels and datasets) and scale boundaries
 * @function populateCandlesChart
 *
 * @param {object} chartData candlestick chart's data and scale boundaries
 *
 */
function populateCandlesChart(chartData) {
  var canvasCandles = document.getElementById("id-candles");
  var ctxCandles = canvasCandles.getContext("2d");
  chartCandles = new Chart(ctxCandles, {
    type: "candlestick",
    data: chartData.data,
    options: {
      responsive: true,
      animation: {
        duration: 300,
      },
      scales: {
        x: {
          // type: 'time',
          min: chartData.xmin,
          max: chartData.xmax,
        },
        y: {
          type: "linear",
        },
      },
      plugins: {
        legend: {
          display: false,
        },
        zoom: {
          pan: {
            enabled: true,
            mode: "x",
            modifierKey: "ctrl",
            scaleMode: "x",
            onPanComplete: viewChanged,
          },
          limits: {
            // axis limits
          },
          zoom: {
            wheel: {
              enabled: true,
              modifierKey: "ctrl",
              speed: 0.3,
            },
            pinch: {
              enabled: true,
            },
            mode: "x",
            scaleMode: "x",
            onZoomComplete: viewChanged,
          },
        },
      },
      onHover: function (evt, elem) {
        evt.native.target.style.cursor = elem[0] ? "pointer" : "default";
      },
    },
  });

  canvasCandles.addEventListener("mousedown", function (evt) {
    if (evt.button === 0 || evt.button === 1) {
      // middle click
      var xPixel = evt.offsetX;
      var xValue = chartCandles.scales.x.getValueForPixel(xPixel);
      handleCandleClick(evt, xValue, chartCandles, evt.button);
    }
  });

  canvasCandles.addEventListener(
    "touchstart",
    function (evt) {
      if (evt.touches.length !== 1) return;

      var rect = canvas.getBoundingClientRect();
      var touch = evt.touches[0];
      var xPixel = touch.clientX - rect.left;
      var xValue = chart.scales.x.getValueForPixel(xPixel);

      longPressTimeout = setTimeout(function () {
        console.log("📱 Long press detected at x:", xValue);
        handleCandleClick(evt, xValue, chartCandles, 1);
      }, 600); // 600ms for long press
    },
    { passive: true },
  );

  canvasCandles.addEventListener("touchend", function () {
    clearTimeout(longPressTimeout);
  });

  canvasCandles.addEventListener("touchmove", function () {
    clearTimeout(longPressTimeout); // Cancel if finger moves
  });
}

/**
 * Create or update bars and candlesticks charts using retrieved charts data
 * @function populateCharts
 *
 * @param {object} chartsData bar and candlestick charts data and scale boundaries
 *
 */
function populateCharts(chartsData) {
  if (typeof chartBars !== "undefined") {
    suppressZoom = true;
    updateChart(chartBars, chartsData.bars);
    updateChart(chartCandles, chartsData.candles);
    suppressZoom = false;
  } else {
    populateBarsChart(chartsData.bars);
    populateCandlesChart(chartsData.candles);
  }
}

/**
 * Show bar chart tab
 * @function showBars
 *
 */
function showBars() {
  $(".tabs").tabs("select", "tbars");
}

/**
 * Show items found in all provided arrays
 *
 * @param {Array.Number} matches
 */
function showMatchedNodes(matches) {
  $(".collapsible").not(".consolidated").hide();
  $(".fitem").hide();
  $(".nfticon").hide();
  if (matches.length === 0) return false;

  var common = matches.shift().filter(function (v) {
    return matches.every(function (a) {
      return a.indexOf(v) !== -1;
    });
  });

  common.forEach(function (id, index) {
    $("#" + id).show();
    $("#" + id)
      .parents(".fitem")
      .show();
    $("#" + id)
      .parents(".collapsible")
      .show();
    $("#" + id)
      .parents(".collapsible")
      .find(".nfticon")
      .each(function (idx) {
        if ($(this).attr("id") === "t" + id) $(this).show();
      });
  });
}

/**
 * Show update tab
 * @function showUpdate
 *
 */
function showUpdate() {
  $(".tabs").tabs("select", "tupdate");
}

/**
 * Locate unit element's parent and scroll browser to it
 *
 * @param {String} label
 *
 */
function scrollToUnit(label) {
  var duration = 250;
  var unit = $(".unit").filter(function () {
    return $(this).text() === label;
  });
  if (typeof unit.get(0) === "undefined") {
    if (label === "NFT") {
      scrollToView(document.getElementById("id-nft"), duration);
      return true;
    } else if (label === "LOFTY") {
      unit = $(".unit").filter(function () {
        return $(this).text().indexOf("LFTY") !== -1;
      });
    }
  }

  var unmoved = scrollToView(unit.get(0), duration);
  var header = unit.parent().parent();
  if (!header.parent().hasClass("active"))
    setTimeout(
      function () {
        header.trigger("click");
      },
      unmoved ? 0 : duration,
    );
}

/**
 * Resize chart if the related tab link is clicked
 * @function tabShow
 *
 * @param {object} tab tab list item link element
 *
 */
function tabShow(tab) {
  if (tab.id === "tbars" && typeof chartBars !== "undefined") {
    chartBars.resize();
  } else if (tab.id === "tcandles" && typeof chartCandles !== "undefined") {
    chartCandles.resize();
  }
}

/**
 * Switch total without NFTs on and off
 *
 */
function toggleTotalNoNft() {
  var value = $(this).prop("checked") ? "y" : "";
  localStorage.setItem("htotalnonft", value);
  setTotalNoNft(value);
}

/**
 * Create or update bars and candlesticks charts using retrieved charts data
 * @function updateChart
 *
 * @param {object} chart chart instance
 * @param {object} data chart data and scale boundaries
 *
 */
function updateChart(chart, data) {
  chart.data = data.data;
  chart.options.scales.x.min = data.xmin;
  chart.options.scales.x.max = data.xmax;
  chart.update();
  chart.resetZoom();
}

/*
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 * SECTION: exports needed by jest testing framework
 * * * * * * * * * * * * * * * * * * * * * * * * * * *
 */

/* istanbul ignore next */
if (typeof exports !== "undefined") {
  module.exports = {
    // * SECTION: Initialization
    initHistoric,
    mainHistoric,
    resetHistoric,
    //  * SECTION: Websocket communication
    messageReceived,
    submitShow,
    submitView,
    // * SECTION: Charts helper functions
    barChartClicked,
    handleCandleClick,
    setUILocked,
    setUILockedBlur,
    viewChanged,
    //  * SECTION: Currency functions
    cur,
    dec6,
    setCurrency,
    toggleCurrency,
    //  * SECTION: Helper functions
    copyToClipboard,
    deferImages,
    filterChange,
    getNodesThatContain,
    isItemInArray,
    populateBarsChart,
    populateCandlesChart,
    populateCharts,
    showBars,
    showMatchedNodes,
    showUpdate,
    scrollToUnit,
    tabShow,
    toggleTotalNoNft,
    updateChart,
  };
}
