/**
 * @file Alerts: open the modal, and show only the fields the subject needs.
 * @author Ivica Paleka
 */
(function () {
  "use strict";

  /** Subjects that name a single asset, mirroring `models.ASSET_SUBJECTS`. */
  var ASSET_SUBJECTS = [
    "asa_price",
    "asa_price_percent",
    "asa_amount",
    "asa_total",
  ];

  /** Subjects expressed as a percentage, mirroring `models.PERCENT_SUBJECTS`. */
  var PERCENT_SUBJECTS = ["total_percent", "asa_price_percent"];

  /** Subjects with no currency, mirroring `models.CURRENCY_SUBJECTS` inverted. */
  var UNITLESS_SUBJECTS = PERCENT_SUBJECTS.concat(["asa_amount"]);

  /**
   * Show the fields this subject needs and hide the rest.
   * Both fields stay mounted (removing loses typed input).
   * @param {Element} root - the panel holding the form.
   * @returns {boolean} whether a form was found to adjust.
   */
  function syncFields(root) {
    var form = root && root.querySelector(".alerts-form");
    if (!form) return false;
    var subject = form.querySelector(".alerts-subject");
    if (!subject) return false;
    var chosen = subject.value;
    var asset = form.querySelector(".alerts-asset-field");
    var window_ = form.querySelector(".alerts-window-field");
    if (asset) asset.hidden = ASSET_SUBJECTS.indexOf(chosen) === -1;
    if (window_) window_.hidden = PERCENT_SUBJECTS.indexOf(chosen) === -1;
    // A percentage is not a currency, so the unit control has nothing to say.
    var units = form.querySelector(".alerts-units");
    if (units) units.hidden = UNITLESS_SUBJECTS.indexOf(chosen) !== -1;
    showCurrent(root);
    return true;
  }

  /**
   * Whether this browser is an iPhone or an iPad.
   * Used for wording only, not feature detection.
   * iPadOS 13+ reports as Macintosh; touch points distinguish.
   * @returns {boolean} whether this is iOS or iPadOS.
   */
  function isApplePortable() {
    // No `|| ""` fallback: every browser has a user agent, so that would be
    // a branch no test could reach.
    var agent = navigator.userAgent;
    if (/iPad|iPhone|iPod/.test(agent)) return true;
    return /Macintosh/.test(agent) && navigator.maxTouchPoints > 1;
  }

  /**
   * Whether the site is running from the Home Screen rather than a tab.
   *
   * @returns {boolean} whether this is an installed PWA.
   */
  function isInstalled() {
    if (navigator.standalone === true) return true;
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(display-mode: standalone)").matches
    );
  }

  /**
   * What to tell the reader about whether alerts can reach them.
   * Feature detection first; user agent only for wording.
   * @returns {string} one of "ok", "ios-install", "ios-old", "unsupported".
   */
  function supportState() {
    if ("PushManager" in window && "serviceWorker" in navigator) return "ok";
    if (!isApplePortable()) return "unsupported";
    // Installed and still no PushManager means the iOS is older than 16.4,
    // which is a different sentence: there is nothing to install.
    return isInstalled() ? "ios-old" : "ios-install";
  }

  /**
   * Reveal the one message that applies, and hide the rest.
   * Copy is in template, not here.
   * @param {Element} root - the modal.
   * @returns {string} the state it showed.
   */
  function showSupport(root) {
    var state = supportState();
    var notes = (root || document).querySelectorAll("[data-support]");
    Array.prototype.forEach.call(notes, function (note) {
      note.hidden = note.getAttribute("data-support") !== state;
    });
    return state;
  }

  /**
   * Open the dialog once htmx has put it in the document.
   *
   * @param {Element} root - the swapped-in content.
   * @returns {boolean} whether a dialog was opened.
   */
  function openModal(root) {
    var dialog = (root || document).querySelector("#alerts-modal");
    if (!dialog || typeof dialog.showModal !== "function") return false;
    if (!dialog.open) dialog.showModal();
    syncFields(dialog);
    showSupport(dialog);
    return true;
  }

  /**
   * Turn a base64url VAPID key into the Uint8Array `subscribe()` wants.
   * Key is base64url for JSON transport; Push API takes bytes.
   * @param {string} key - the public key, base64url.
   * @returns {Uint8Array} its bytes.
   */
  function vapidKeyBytes(key) {
    var padded = (key + "=".repeat((4 - (key.length % 4)) % 4))
      .replace(/-/g, "+")
      .replace(/_/g, "/");
    var raw = atob(padded);
    var bytes = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    return bytes;
  }

  /**
   * Put the block into the state the server would render it in now.
   * Warning and button label are server-rendered from subscribed_browsers.
   * @param {Element} root - the `.alerts-enable` element.
   */
  function markEnabled(root) {
    var warning = root.querySelector(".alerts-warning");
    if (warning && warning.parentNode) {
      warning.parentNode.removeChild(warning);
    }
    var button = root.querySelector(".alerts-enable-btn");
    if (button) button.textContent = "This browser is on";
  }

  /**
   * Ask permission, register the worker, subscribe, and tell the server.
   * Four independent failure modes, each reported to reader.
   * @param {Element} root - the `.alerts-enable` element carrying the urls.
   * @returns {Promise<string>} what happened, for the state line and the tests.
   */
  function enablePush(root) {
    var say = function (message) {
      var state = root.querySelector(".alerts-enable-state");
      if (state) state.textContent = message;
      return message;
    };

    if (supportState() !== "ok") {
      // The notice above the button already explains which case this is.
      return Promise.resolve(say("Not available in this browser."));
    }

    return Notification.requestPermission()
      .then(function (permission) {
        if (permission !== "granted") {
          // Not an error, not retried: refusal is an answer.
          throw new Error("Notifications are blocked in this browser's settings.");
        }
        return navigator.serviceWorker.register(root.dataset.workerUrl);
      })
      .then(function (registration) {
        return registration.pushManager.subscribe({
          // Required by every browser: a push must result in something the
          // reader sees. We always show one, so this costs nothing.
          userVisibleOnly: true,
          applicationServerKey: vapidKeyBytes(root.dataset.vapidKey),
        });
      })
      .then(function (subscription) {
        return fetch(root.dataset.subscribeUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: JSON.stringify(subscription.toJSON()),
        });
      })
      .then(function (response) {
        if (!response.ok) throw new Error("The server refused the subscription.");
        markEnabled(root);
        return say("This browser is on.");
      })
      .catch(function (error) {
        return say(error.message || "Could not enable notifications.");
      });
  }

  /**
   * Read the CSRF cookie, which the fetch above has to carry.
   *
   * @returns {string} the token, or "" when there is none.
   */
  function csrfToken() {
    var match = document.cookie.match(/(^|;)\s*csrftoken\s*=\s*([^;]+)/);
    return match ? match.pop() : "";
  }

  document.addEventListener("click", function (event) {
    var enabler = event.target.closest && event.target.closest(".id-alerts-enable");
    if (enabler) {
      var host = enabler.closest(".alerts-enable");
      if (host) enablePush(host);
    }
    var closer = event.target.closest && event.target.closest(".id-alerts-close");
    if (closer) {
      var dialog = document.getElementById("alerts-modal");
      if (dialog && dialog.open) dialog.close();
    }
  });

  // The subject select is replaced on every swap, so this is delegated from the
  // document rather than bound to it - the same reason `showmore.js` delegates.
  document.addEventListener("change", function (event) {
    // **The direction decides which side of the figure to offer**, so a reader
    // switching from "rises above" to "falls below" must not be left holding a
    // threshold the price is already past.
    if (event.target.classList.contains("alerts-direction")) {
      suggest(event.target.closest(".alerts-panel") || document);
      return;
    }
    if (event.target.classList.contains("alerts-subject")) {
      // No `|| document` fallback: the select is rendered inside the panel, so
      // a miss is impossible - and `syncFields` already answers false for a
      // null root, which is the honest behaviour if it ever were.
      syncFields(event.target.closest(".alerts-panel"));
    }
  });

  /**
   * React to an htmx swap: open the modal that arrived, or re-sync a panel.
   * event.target is the button, not swapped content; uses detail.ctx.target.
   * Only two swaps acted on: modal open and panel replace.
   * @param {Event} event - htmx's after-swap event.
   * @returns {boolean} whether this swap was one of ours.
   */
  function handleSwap(event) {
    var ctx = event.detail && event.detail.ctx;
    var swapped = (ctx && ctx.target) || event.target;
    if (!swapped || !swapped.querySelector) return false;

    if (swapped.querySelector("#alerts-modal")) {
      openModal(swapped);
      syncCount(swapped.querySelector(".alerts-panel"));
      resolveAsset(swapped.querySelector(".alerts-panel") || swapped);
      return true;
    }
    // A create or a delete replaces the panel by `outerHTML`, which leaves
    // `ctx.target` pointing at the element that was replaced - detached, and
    // useless to sync. It still carries the class, so the live panel is looked
    // up in the document and the detached one is only used to recognise the
    // swap.
    //
    // By class rather than by id, because that is what `syncFields` itself
    // works from and what the jest fixture and the template are guaranteed to
    // agree on.
    if (swapped.classList && swapped.classList.contains("alerts-panel")) {
      var panel = document.querySelector(".alerts-panel") || swapped;
      syncFields(panel);
      syncCount(panel);
      showCurrent(panel);
      resolveAsset(panel);
      return true;
    }
    return false;
  }

  /**
   * Record which unit the reader is typing their threshold in.
   * Hidden input is what form posts; buttons are visible state.
   * @param {Element} button - the pressed unit button.
   * @returns {boolean} whether the unit was recorded.
   */
  function chooseUnit(button) {
    var field = button.closest(".alerts-threshold-field");
    if (!field) return false;
    var hidden = field.querySelector(".alerts-unit-value");
    if (!hidden) return false;

    hidden.value = button.getAttribute("data-unit") || "algo";
    var buttons = field.querySelectorAll(".id-alerts-unit");
    Array.prototype.forEach.call(buttons, function (other) {
      other.setAttribute("aria-pressed", other === button ? "true" : "false");
    });
    showCurrent(field.closest(".alerts-panel") || document);
    return true;
  }

  /**
   * Format a price without losing a small one to rounding.
   * Threshold 0.0000123 would show as 0.00 with toFixed(2).
   * @param {number} value - the figure.
   * @returns {string} it, readably.
   */
  /** Suggest offset: 5% - far enough to not trigger on first block, near enough to be plausible. */
  var SUGGEST_OFFSET = 0.05;

  function trim(value) {
    if (value >= 1) return value.toFixed(2);
    // Enough places to keep four significant digits on a small number.
    return value.toPrecision(4).replace(/0+$/, "").replace(/\.$/, "");
  }

  /**
   * Show what the watched figure is now, in the unit the reader chose.
   * Threshold shown, not filled (arms on first reading, fires on crossing).
   * Asset price not published here; only portfolio total known.
   * @param {Element} root - the panel.
   * @returns {string} what was shown, for the tests.
   */
  function currentFigure(root) {
    var note = root && root.querySelector(".alerts-now");
    var form = root && root.querySelector(".alerts-form");
    if (!note || !form) return null;

    var subject = form.querySelector(".alerts-subject");
    if (!subject) return null;
    var unitField = form.querySelector(".alerts-unit-value");
    var chosen = unitField ? unitField.value : "algo";
    var total = parseFloat(note.getAttribute("data-current-total"));
    // **ALGO per USD**, which is what `priceusdc` holds - about 4 when ALGO
    // is $0.25. So an ALGO figure is *divided* by it to reach dollars. This
    // read it as ALGO's dollar price and multiplied, which was wrong by the
    // square of the rate; `address.js` has always divided, and is the
    // reference.
    var rate = parseFloat(note.getAttribute("data-algo-per-usd"));

    if (subject.value === "total_value" && isFinite(total)) {
      if (chosen === "usd") {
        return isFinite(rate) && rate > 0
          ? { value: total / rate, unit: "usd" }
          : null;
      }
      return { value: total, unit: "algo" };
    }
    if (subject.value === "asa_price") {
      // **Derived, because the two sides speak different currencies.** The
      // search row carries the asset's price in *USD*; the threshold is stored
      // in ALGO. Dividing by what one ALGO costs is the whole conversion, and
      // showing the USD figure beside an ALGO threshold without it would be the
      // most dangerous version of this feature.
      var assetUsd = parseFloat(note.getAttribute("data-asset-usd"));
      if (isFinite(assetUsd) && isFinite(rate) && rate > 0) {
        return chosen === "usd"
          ? { value: assetUsd, unit: "usd" }
          : { value: assetUsd * rate, unit: "algo" };
      }
    }
    // `asa_total` and `asa_amount` are about *this reader's holding* - its
    // value and its count - and neither is published to this modal. The panel
    // is rendered for a page before an asset has been chosen, and the picker
    // answers with the asset's price, not with how much of it anybody holds.
    // Nothing rather than the wrong number, here and in the suggestion.
    return null;
  }

  function showCurrent(root) {
    var note = root && root.querySelector(".alerts-now");
    if (!note) return "";
    var figure = currentFigure(root);
    var text = "";
    if (figure) {
      text =
        figure.unit === "usd"
          ? "Now $" + trim(figure.value)
          : "Now " + trim(figure.value) + " ALGO";
    }
    note.textContent = text;
    suggest(root);
    return text;
  }

  /**
   * Offer a threshold a little way past what the figure is now.
   * Threshold != current value (arms on first reading, fires on crossing).
   * Offset for direction; never over what reader typed (data-suggested tracks).
   * @param {Element} root - the panel.
   * @returns {string} what was offered, or "" when nothing was.
   */
  function suggest(root) {
    var form = root && root.querySelector(".alerts-form");
    if (!form) return "";
    var input = form.querySelector(".alerts-threshold");
    if (!input) return "";
    if (input.value && input.value !== input.getAttribute("data-suggested")) {
      return "";
    }
    var figure = currentFigure(root);
    if (!figure) return "";

    var direction = form.querySelector(".alerts-direction");
    var up = !direction || direction.value === "up";
    var text = trim(figure.value * (up ? 1 + SUGGEST_OFFSET : 1 - SUGGEST_OFFSET));
    input.value = text;
    input.setAttribute("data-suggested", text);
    return text;
  }

  /**
   * Copy the panel's counts onto the toolbar the reader can actually see.
   * Swap replaces modal; badge not in it. Read from panel.
   * @param {Element} panel - the freshly swapped panel.
   * @returns {boolean} whether the toolbar was updated.
   */
  function syncCount(panel) {
    var toolbar = document.getElementById("id-alerts");
    if (!panel || !toolbar) return false;
    var kept = panel.getAttribute("data-rules-kept");
    var left = panel.getAttribute("data-rules-left");
    if (kept === null || left === null) return false;

    var badge = toolbar.querySelector(".alerts-count");
    if (badge) {
      badge.textContent = kept;
      badge.hidden = kept === "0";
    }
    toolbar.setAttribute("data-rules-left", left);

    var button = toolbar.querySelector(".alerts-open");
    if (button) {
      // The template writes this when the allowance is spent; the modal is the
      // only place that number changes, so it has to be maintained here too.
      if (left === "0") button.setAttribute("data-at-limit", "true");
      else button.removeAttribute("data-at-limit");
    }
    return true;
  }

  /**
   * Move the alerts toolbar into the page's action row, beside Dust Sweep.
   * Partial lands in wrong place; rendered hidden to avoid jump.
   * @returns {boolean} whether the toolbar was moved.
   */
  function placeToolbar() {
    var toolbar = document.getElementById("id-alerts");
    if (!toolbar) return false;
    var slot = document.getElementById("id-dustsweep-slot");
    var moved = !!slot && slot !== toolbar.parentNode;
    if (moved) slot.appendChild(toolbar);
    toolbar.hidden = false;
    return moved;
  }

  /**
   * Record the asset a reader picked out of the search results.
   * Hidden field is what form posts; typing != choosing.
   * Unit travels with id; row has only price.
   * @param {Element} row - the clicked result row.
   * @param {Element} [field] - the field to record it in.
   * @returns {boolean} whether an asset was recorded.
   */
  function chooseAsset(row, field) {
    field = field || (row.closest && row.closest(".alerts-asset-field"));
    if (!field) return false;
    var hidden = field.querySelector(".alerts-asset-id");
    var button = field.querySelector(".alerts-assetbtn");
    if (!hidden || !button) return false;

    hidden.value = row.getAttribute("data-id") || "";
    // Unit travels with id for server-side notification.
    var unit = field.querySelector(".alerts-asset-unit");
    if (unit) unit.value = row.getAttribute("data-unit") || "";
    var text = button.querySelector(".alerts-assetbtn-text");
    if (text) {
      text.textContent =
        (row.getAttribute("data-unit") || "") + "  #" + hidden.value;
    }
    var icon = button.querySelector(".alerts-assetbtn-icon");
    if (icon) {
      icon.src = row.getAttribute("data-icon") || "";
      icon.hidden = !icon.src;
    }
    // Row is only place this price exists.
    var note = (field.closest(".alerts-panel") || document).querySelector(
      ".alerts-now"
    );
    if (note) note.setAttribute("data-asset-usd", row.getAttribute("data-usdc-price") || "");

    // The asset is now on the button, so the picker has done its job.
    togglePicker(field, false);
    showCurrent(field.closest(".alerts-panel") || document);
    return true;
  }

  /**
   * Look up the price of an asset the *server* chose, not the reader.
   * Reference price from search results; bound forms lack it.
   * Reuses swap_assets endpoint; silent on failure; exact id match only.
   * @param {Element} root - the panel.
   * @returns {boolean} whether a lookup was started.
   */
  function resolveAsset(root) {
    var field = root && root.querySelector(".alerts-asset-field");
    if (!field) return false;
    var hidden = field.querySelector(".alerts-asset-id");
    var note = root.querySelector(".alerts-now");
    if (!hidden || !hidden.value || !note) return false;
    // Already known - the reader picked it a moment ago, and asking again
    // would be a request per swap for an answer already on the page.
    if (note.getAttribute("data-asset-usd")) return false;

    var search = field.querySelector(".alerts-asset-search");
    var url = search && search.getAttribute("hx-get");
    if (!url || typeof fetch !== "function") return false;

    var wanted = hidden.value;
    fetch(url + "?q=" + encodeURIComponent(wanted), {
      headers: { "HX-Request": "true" },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.ok ? response.text() : "";
      })
      .then(function (html) {
        if (!html) return;
        // Parsed off-page: results container belongs to picker.
        var holder = document.createElement("div");
        holder.innerHTML = html;
        var row = holder.querySelector(
          '.id-swap-asset-option[data-id="' + wanted + '"]'
        );
        // Only exact id match; loose match hangs wrong asset's price.
        if (row) chooseAsset(row, field);
      })
      .catch(function () {});
    return true;
  }

  /**
   * Open or close an asset field's picker.
   *
   * @param {Element} field - the `.alerts-asset-field`.
   * @param {boolean} open - whether it should be open.
   * @returns {boolean} whether a picker was found.
   */
  function togglePicker(field, open) {
    var picker = field && field.querySelector(".alerts-picker");
    var button = field && field.querySelector(".alerts-assetbtn");
    if (!picker || !button) return false;
    picker.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      var search = picker.querySelector(".alerts-asset-search");
      if (search) search.focus();
    }
    return true;
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest) return;

    // Scoped to widget's own results; swap window renders same rows.
    var row = event.target.closest(".alerts-asset-results .id-swap-asset-option");
    if (row) {
      chooseAsset(row);
      return;
    }

    var button = event.target.closest(".id-alerts-assetbtn");
    if (button) {
      var field = button.closest(".alerts-asset-field");
      togglePicker(field, button.getAttribute("aria-expanded") !== "true");
      return;
    }

    var unit = event.target.closest(".id-alerts-unit");
    if (unit) chooseUnit(unit);
  });

  placeToolbar();

  // The partial itself arrives by swap, so the toolbar may not exist yet when
  // this script first runs - the same reason `handleSwap` exists at all.
  document.body.addEventListener("htmx:after:swap", placeToolbar);

  document.body.addEventListener("htmx:after:swap", handleSwap);

  // Published so page knows script is listening.
  window.asastatsAlerts = {
    handleSwap: handleSwap,
    placeToolbar: placeToolbar,
    syncCount: syncCount,
    chooseAsset: chooseAsset,
    chooseUnit: chooseUnit,
    showCurrent: showCurrent,
    currentFigure: currentFigure,
    suggest: suggest,
    resolveAsset: resolveAsset,
    togglePicker: togglePicker,
    openModal: openModal,
    syncFields: syncFields,
  };

  /* istanbul ignore next -- exported for the jest suite only */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      syncFields: syncFields,
      handleSwap: handleSwap,
      placeToolbar: placeToolbar,
      syncCount: syncCount,
      chooseAsset: chooseAsset,
      chooseUnit: chooseUnit,
      showCurrent: showCurrent,
      currentFigure: currentFigure,
      suggest: suggest,
      resolveAsset: resolveAsset,
      togglePicker: togglePicker,
      openModal: openModal,
      supportState: supportState,
      showSupport: showSupport,
      isApplePortable: isApplePortable,
      isInstalled: isInstalled,
      enablePush: enablePush,
      markEnabled: markEnabled,
      vapidKeyBytes: vapidKeyBytes,
    };
  }
})();
