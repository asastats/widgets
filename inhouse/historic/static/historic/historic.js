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
/**
 * The charts exactly as the engine sent them, which is always in ALGO.
 *
 * The engine does not know which currency this reader is looking at, so its
 * payload is the source and the drawn charts are a view of it. Kept because a
 * currency switch has to rescale from these original figures: converting the
 * drawn ones would divide by the price again on every flip of the switch, and
 * the charts would shrink towards zero as the reader played with it.
 */
var chartsSource;
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
function initHistoric() {}

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
  // Nothing to construct: the disclosures are native <details>, the
  // confirmation is a native <dialog>, and the tabs follow the same shape as
  // the login dialog's (static/js/authmodal.js) -- anchors carrying
  // `aria-selected` over panels toggled with `hidden`. This used to call
  // `.collapsible()`, `.modal()` and `.tabs()`, all Materialize, none of it
  // loaded on this page any more; the first threw and abandoned jQuery's
  // ready queue, taking every binding below it. The widget was inert.
  $("[role=tablist]").on("click", "[role=tab]", tabClick);
  // Delegated from the document, not bound to the thumbnails: rows arrive in
  // htmx websocket batches long after this runs, and anything bound directly
  // would cover only the rows that happened to exist at the time.
  $(document).on("mouseover", ".nfticon", nftShowPreview);
  $(document).on("mouseleave", ".nfticon", nftHidePreview);
  $(document).on("click", ".nfticon", nftHidePreview);
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
  // Same as mainHistoric: no accordion or tooltip widgets to construct. The
  // tooltips are CSS-only (`data-tip`), so they work in re-rendered markup
  // without being re-initialised -- which this function existed partly to do.
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

// True while the assets section streams in OOB fragments; suppresses the
// per-frame resetHistoric() so init runs once, on assets_end.
var assetsStreaming = false;

// Instant-feedback state for a segment click: a "request in flight" guard, a
// watchdog timer, and the pending-segment chart marker.
var requestPending = false;
var assetsTimeout = null;
var pendingMarker = null;

// Chart.js inline plugin: draws a dashed vertical line at the clicked segment
// while its timestamp is being fetched. Defensive so it can never break a chart.
var pendingMarkerPlugin = {
  id: "pendingMarker",
  afterDraw: function (chart) {
    if (!pendingMarker || pendingMarker.chart !== chart) {
      return;
    }
    try {
      var x = chart.scales.x.getPixelForValue(pendingMarker.value);
      if (x === null || isNaN(x)) {
        return;
      }
      var ctx = chart.ctx;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x, chart.chartArea.top);
      ctx.lineTo(x, chart.chartArea.bottom);
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = "rgba(0, 0, 0, 0.45)";
      ctx.stroke();
      ctx.restore();
    } catch (e) {
      // Never let the marker interfere with chart rendering.
    }
  },
};

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
    } else if (message.type === "assets_begin") {
      // Server responded and streaming has started; stop the click watchdog.
      clearAssetsTimeout();
      // Scaffold + OOB batches follow as HTML frames; defer init to the end.
      assetsStreaming = true;
    } else if (message.type === "assets_end") {
      // Every assets fragment has arrived; clear the loading state and init
      // the now-complete #id-assets DOM.
      assetsStreaming = false;
      clearAssetsPending();
      resetHistoric();
    }
  } catch (e) {
    // A streamed HTML fragment (scaffold or OOB batch) is swapped by htmx and
    // init is deferred to assets_end; every other raw-HTML frame re-inits now.
    if (!assetsStreaming) {
      resetHistoric();
    }
  }
}

/**
 * Show an instant loading placeholder in the assets panel.
 *
 * Called synchronously on a segment click, before the WebSocket request is sent,
 * so the click is acknowledged with zero latency. The incoming scaffold frame
 * OOB-replaces #id-assets, so no explicit teardown is needed on success.
 *
 * @function showAssetsLoading
 * @param {String} [whenText] human label of the clicked point, echoed if given
 *
 */
function showAssetsLoading(whenText) {
  var message = whenText
    ? "Loading portfolio for " + whenText
    : "Loading portfolio\u2026";
  $("#id-assets")
    .attr("aria-busy", "true")
    .html(
      '<div class="col s12 center-align assets-loading">' +
        '<div class="preloader-wrapper active">' +
        '<div class="spinner-layer">' +
        '<div class="circle-clipper left"><div class="circle"></div></div>' +
        '<div class="gap-patch"><div class="circle"></div></div>' +
        '<div class="circle-clipper right"><div class="circle"></div></div>' +
        "</div></div>" +
        '<p class="assets-loading-text">' +
        message +
        "</p>" +
        "</div>",
    );
}

/**
 * Replace the loading placeholder with a retryable error message.
 * @function showAssetsError
 *
 */
function showAssetsError() {
  clearAssetsPending();
  $("#id-assets")
    .removeAttr("aria-busy")
    .html(
      '<div class="col s12 center-align assets-loading">' +
        '<p class="assets-loading-text">Couldn\'t load this timestamp. Please try again.</p>' +
        "</div>",
    );
}

/**
 * Start the click-to-response watchdog so the spinner never hangs.
 * @function startAssetsTimeout
 *
 */
function startAssetsTimeout() {
  clearAssetsTimeout();
  assetsTimeout = setTimeout(showAssetsError, 30000);
}

/**
 * Cancel the click-to-response watchdog.
 * @function clearAssetsTimeout
 *
 */
function clearAssetsTimeout() {
  if (assetsTimeout) {
    clearTimeout(assetsTimeout);
    assetsTimeout = null;
  }
}

/**
 * Redraw the chart holding the pending-segment marker.
 * @function drawPendingMarker
 *
 */
function drawPendingMarker() {
  if (
    pendingMarker &&
    pendingMarker.chart &&
    typeof pendingMarker.chart.render === "function"
  ) {
    // render() repaints (running the marker plugin) without the update
    // lifecycle, so it never fires zoom/pan-complete callbacks.
    pendingMarker.chart.render();
  }
}

/**
 * Clear the in-flight request state: pending flag, watchdog and chart marker.
 * @function clearAssetsPending
 *
 */
function clearAssetsPending() {
  requestPending = false;
  clearAssetsTimeout();
  // The loading bar goes with the pending state. `mainHistoric` starts it on
  // load and `setUILocked` drives it after that, but a bundle whose data is
  // already computed never gets an unlock message -- the assets simply stream
  // in and stop -- so nothing took it down and it swept for as long as the page
  // stayed open. It was invisible until the rules for it were written, which is
  // why it went unnoticed.
  $(".historic-progress").removeClass("progress");
  if (pendingMarker) {
    var chart = pendingMarker.chart;
    pendingMarker = null;
    if (chart && typeof chart.render === "function") {
      chart.render(); // repaint to erase the marker (no zoom/pan callbacks)
    }
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
function submitShow(xVal, label, whenText) {
  document.getElementById("show-x-val").value = xVal;
  document.getElementById("show-label").value = label;

  if (requestPending) {
    // A timestamp fetch is already in flight; the inputs are staged but we
    // don't send a duplicate request or restart the loading state.
    return;
  }
  requestPending = true;
  showAssetsLoading(whenText);
  drawPendingMarker();

  htmx.trigger("#id-show", "submit");
  startAssetsTimeout();
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
      var whenLabel = (evt.chart.data.labels || [])[selectedIdx];
      pendingMarker = { chart: chartBars, value: selectedIdx };
      return submitShow(
        selectedIdx,
        label,
        typeof whenLabel === "string" ? whenLabel : null,
      );
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

  pendingMarker = { chart: chartCandles, value: timestamp };
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
 * Give an element a tooltip carrying the given text.
 * @function setHistoricTip
 *
 * Named apart from `consolidated.js`'s `setTip`, which this page also loads.
 * Two different functions under one global name is decided by script order --
 * this file loads second, so its version silently replaced the other's for
 * every caller, including callers inside that other file. The behaviours happen
 * to be compatible today; the arrangement is not one to leave lying around.
 *
 * The class is added here rather than rendered into the templates because the
 * text is what makes the tooltip worth having, and it is written from here --
 * markup that carried the class without the text would offer an empty box.
 * Only `.pricetip` names `.htip` in a template, because it arrives with a tip
 * already rendered into it.
 *
 * This is also where the figures got their tooltip *payload* and no way to show
 * it: `data-tip` was written to every `span.val` while only `.pricetip` carried
 * the class DaisyUI styles, so every other figure computed a tip on each switch
 * that nothing could ever display. And the `data-position` written beside it
 * was Materialize's API, which has done nothing since the conversion --
 * `.htip-bottom` is this widget's own and actually moves the tip.
 *
 * @param {Element} element element to give a tooltip to
 * @param {String} text the tooltip's text
 *
 */
function setHistoricTip(element, text) {
  element.dataset.tip = text;
  element.classList.add("htip");
  // A tooltip drawn with `content: attr(data-tip)` is not reliably announced --
  // generated content is not in the accessibility tree in any dependable way --
  // so an element that wants its tip *read* points `aria-describedby` at a
  // visually hidden span and this keeps that span in step with the switch.
  // Only the total does; see the comment on it in `assets.html`.
  var describedBy = element.getAttribute("aria-describedby");
  if (describedBy) {
    var note = document.getElementById(describedBy);
    if (note) note.textContent = text;
  }
  // Below rather than above for the category row, which sits at the top of an
  // open card where an upward tip is clipped.
  element.classList.toggle(
    "htip-bottom",
    element.classList.contains("cons-value")
  );
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
      setHistoricTip(this, cur(total * price) + " ALGO (" + dec6(price) + " ALGO/USD)");
      this.innerHTML = cur(total) + " USD";
    });
    $("span.val").each(function () {
      this.innerHTML = cur(this.dataset.val / price) + " USD";
      setHistoricTip(this, cur(this.dataset.val) + " ALGO");
    });
  } else {
    $(".pricetip").each(function () {
      setHistoricTip(this, cur(total) + " USD (" + dec6(pricealgo) + " USD/ALGO)");
      this.innerHTML = cur(total * price) + " ALGO";
    });
    $("span.val").each(function () {
      this.innerHTML = cur(this.dataset.val) + " ALGO";
      setHistoricTip(this, cur(this.dataset.val / price) + " USD");
    });
  }
  // The charts follow the switch too. This used to call `setTotalCharts()`,
  // which does not exist in this widget and never did: `setCurrency` was copied
  // from the website, where that function retitles the allocation doughnuts,
  // and the call came across while the function did not. So every switch threw
  // a ReferenceError here -- after the figures had been rewritten, before the
  // checkbox was synced -- and the candles and bars stayed in ALGO.
  setChartsCurrency(code, price);

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
 * Automatically handles 404 fallbacks for missing CDN images.
 * @function deferImages
 *
 * @param {Array.<object>} images Array of image elements
 *
 */
function deferImages(images) {
  for (var i = 0; i < images.length; i++) {
    var img = images[i];
    var dataSrc = img.getAttribute("data-src");

    if (dataSrc) {
      // Attach the error handler for large NFTs BEFORE setting the new source
      img.onerror = function () {
        this.onerror = null; // Prevent infinite loop if the fallback is missing
        this.src = "https://cdn.asastats.com/thumbnails/nft.png";
      };

      // Trigger the actual image load
      img.setAttribute("src", dataSrc);
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
  // snippets/modal_confirm.html is a native <dialog> now, so there is no
  // M.Modal instance to fetch. The guard is for jsdom, which implements
  // <dialog> as an ordinary element.
  var modal = document.querySelector("#id_modalconfirm");
  if (modal && modal.showModal)
    modal.showModal();
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
    plugins: [pendingMarkerPlugin],
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
    plugins: [pendingMarkerPlugin],
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

      var rect = canvasCandles.getBoundingClientRect(); // fixed canvas -> canvasCandles
      var touch = evt.touches[0];
      var xPixel = touch.clientX - rect.left;
      var xValue = chartCandles.scales.x.getValueForPixel(xPixel); // fixed chart -> chartCandles

      longPressTimeout = setTimeout(function () {
        console.log("📱 Long press detected at x:", xValue);
        handleCandleClick(evt, xValue, chartCandles, 1);
      }, 600);
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
  chartsSource = chartsData;
  var charts = chartsInCurrency(chartsData, currentCurrency(), currentPrice());

  if (typeof chartBars !== "undefined") {
    suppressZoom = true;
    updateChart(chartBars, charts.bars);
    updateChart(chartCandles, charts.candles);
    suppressZoom = false;
  } else {
    populateBarsChart(charts.bars);
    populateCandlesChart(charts.candles);
  }
}

/**
 * Return the currency the reader has chosen.
 * @function currentCurrency
 *
 * @returns {String} "ALGO" or "USD"
 *
 */
function currentCurrency() {
  return localStorage.getItem("hcur") || "ALGO";
}

/**
 * Return the ALGO price of one USD, as the rendered page carries it.
 * @function currentPrice
 *
 * @returns {String|null} the price, or null when the page has no figures yet
 *
 */
function currentPrice() {
  var elem = $(".pricetip")[0];
  return typeof elem === "undefined" ? null : elem.dataset.price;
}

/**
 * Return both charts' data expressed in the given currency.
 * @function chartsInCurrency
 *
 * @param {object} source charts payload as the engine sent it, in ALGO
 * @param {String} code currency code the reader has chosen
 * @param {String|Number} price ALGO per USD
 *
 * @returns {object} charts payload to draw
 *
 */
function chartsInCurrency(source, code, price) {
  var rate = parseFloat(price);
  if (code !== "USD" || isNaN(rate) || rate === 0) return source;

  return {
    bars: chartInCurrency(source.bars, rate),
    candles: chartInCurrency(source.candles, rate),
  };
}

/**
 * Return one chart's data with every money figure divided by the ALGO price.
 * @function chartInCurrency
 *
 * @param {object} chartData one chart's data and scale boundaries
 * @param {Number} rate ALGO per USD
 *
 * @returns {object} a copy, scaled
 *
 */
function chartInCurrency(chartData, rate) {
  if (!chartData || !chartData.data) return chartData;

  var datasets = (chartData.data.datasets || []).map(function (dataset) {
    var scaled = Object.assign({}, dataset);
    scaled.data = (dataset.data || []).map(function (point) {
      return pointInCurrency(point, rate);
    });
    return scaled;
  });

  // Copied rather than edited in place: `chartsSource` has to stay in ALGO for
  // the next switch, and Chart.js keeps a reference to whatever it is handed.
  return Object.assign({}, chartData, {
    data: Object.assign({}, chartData.data, { datasets: datasets }),
  });
}

/**
 * Money keys on a chart point.
 *
 * A candle carries `o`, `h`, `l` and `c` -- and also `x` and the four
 * `ot`/`ht`/`lt`/`ct` timestamps that `handleCandleClick` reads to ask the
 * server about a moment in time. Dividing one of those by the ALGO price would
 * ask for a date in 1970, so the list is explicit rather than "every number".
 */
var CHART_MONEY_KEYS = ["o", "h", "l", "c", "y"];

/**
 * Return one chart point with its money figures divided by the ALGO price.
 * @function pointInCurrency
 *
 * @param {Number|String|object} point a bar height or a candle
 * @param {Number} rate ALGO per USD
 *
 * @returns {Number|String|object} the point, scaled
 *
 */
function pointInCurrency(point, rate) {
  if (point === null || typeof point !== "object") {
    return scaleFigure(point, rate);
  }

  var scaled = Object.assign({}, point);
  CHART_MONEY_KEYS.forEach(function (key) {
    if (key in scaled) scaled[key] = scaleFigure(scaled[key], rate);
  });
  return scaled;
}

/**
 * Divide one figure by the ALGO price, leaving anything unparseable alone.
 * @function scaleFigure
 *
 * @param {Number|String} value figure in ALGO
 * @param {Number} rate ALGO per USD
 *
 * @returns {Number|String} the figure in USD, or `value` if it is not a number
 *
 */
function scaleFigure(value, rate) {
  var figure = parseFloat(value);
  return isNaN(figure) ? value : figure / rate;
}

/**
 * Redraw both charts in the currency the reader has just chosen.
 * @function setChartsCurrency
 *
 * @param {String} code currency code the reader has chosen
 * @param {String|Number} price ALGO per USD
 *
 */
function setChartsCurrency(code, price) {
  if (typeof chartsSource === "undefined") return;
  if (typeof chartBars === "undefined") return;

  var charts = chartsInCurrency(chartsSource, code, price);
  // The data only, not `updateChart`: that resets the zoom, and a reader who
  // has panned to a week in March did not ask to be sent back to the whole
  // range because they wanted to read the figures in dollars. The x axis is
  // time and a currency does not move it.
  //
  // Guarded for the same reason: whatever the redraw stirs up, this is not a
  // view change, and letting one escape would post the reader's unchanged
  // range back to the server on every flip of the switch.
  suppressZoom = true;
  chartBars.data = charts.bars.data;
  chartCandles.data = charts.candles.data;
  chartBars.update();
  chartCandles.update();
  suppressZoom = false;
}

/**
 * Show bar chart tab
 * @function showBars
 *
 */
function showBars() {
  selectTab("tbars");
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
  // The engine has no data for this timestamp yet: stop the loading state
  // and reveal the update tab.
  clearAssetsPending();
  $("#id-assets").removeAttr("aria-busy").empty();
  selectTab("tupdate");
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
function tabShow(panelId) {
  var panel = document.getElementById(panelId);
  if (!panel) return false;

  Array.prototype.forEach.call(
    document.querySelectorAll(".historic-tab-panel"),
    function (child) {
      child.hidden = child !== panel;
    }
  );
  Array.prototype.forEach.call(
    document.querySelectorAll('[role="tab"]'),
    function (link) {
      link.setAttribute(
        "aria-selected",
        String(link.getAttribute("href") === "#" + panelId)
      );
    }
  );

  // Chart.js sizes a canvas to its container, and a container that was hidden
  // when the chart was built has no size -- so a chart revealed by a tab
  // switch has to be told to measure again.
  if (panelId === "tbars" && typeof chartBars !== "undefined") {
    chartBars.resize();
  } else if (panelId === "tcandles" && typeof chartCandles !== "undefined") {
    chartCandles.resize();
  }
  return true;
}


/**
 * Reveal the panel a clicked tab points at.
 * @function tabClick
 *
 * @param {jQuery} event Triggered click event object
 *
 */
function tabClick(event) {
  event.preventDefault();
  tabShow((this.getAttribute("href") || "").replace("#", ""));
}


/**
 * Select a tab by panel id, as the Materialize `tabs("select", id)` call did.
 * @function selectTab
 *
 * @param {String} panelId id of the panel to reveal
 *
 */
function selectTab(panelId) {
  tabShow(panelId);
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

/**
 * Remove the NFT preview, if one is open.
 *
 */
function nftHidePreview() {
  var preview = document.getElementById("id-nft-preview");
  if (preview) preview.remove();
}


/**
 * Show the full-size NFT image while its thumbnail is hovered.
 *
 * The portfolio page has had this since before the conversion; these rows
 * carry the same `data-path`, so the only thing missing here was the handler.
 *
 * Built as elements rather than an HTML string: an engine-supplied path
 * containing a quote could close the attribute and inject markup. Setting
 * `.src` cannot do that whatever the value.
 *
 */
function nftShowPreview() {
  nftHidePreview();
  if (!this.dataset.path) return;

  var preview = document.createElement("div");
  preview.id = "id-nft-preview";
  preview.className = "nftpreview";
  var image = document.createElement("img");
  image.src = this.dataset.path;
  image.alt = this.alt || "";
  preview.appendChild(image);

  var box = this.getBoundingClientRect();
  preview.style.top = (box.bottom + window.scrollY + 8) + "px";
  preview.style.left = (box.left + window.scrollX) + "px";
  document.body.appendChild(preview);
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
    showAssetsLoading,
    showAssetsError,
    clearAssetsPending,
    pendingMarkerPlugin,
    // * SECTION: Charts helper functions
    barChartClicked,
    handleCandleClick,
    setUILocked,
    setUILockedBlur,
    viewChanged,
    //  * SECTION: Currency functions
    cur,
    dec6,
    setHistoricTip,
    setCurrency,
    toggleCurrency,
    chartInCurrency,
    chartsInCurrency,
    currentCurrency,
    currentPrice,
    pointInCurrency,
    scaleFigure,
    setChartsCurrency,
    //  * SECTION: Helper functions
    copyToClipboard,
    deferImages,
    filterChange,
    getNodesThatContain,
    isItemInArray,
    nftHidePreview,
    nftShowPreview,
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
