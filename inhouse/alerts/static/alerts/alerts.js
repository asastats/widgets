/**
 * @file Alerts: open the modal, and show only the fields the subject needs.
 * @author Ivica Paleka
 *
 * Almost everything is htmx: the modal is fetched by the control, and creating
 * or removing a rule swaps the panel the server re-rendered. What is left for
 * script is the part htmx has no opinion about - a native <dialog> has to be
 * opened by `showModal()`, and which fields a subject needs is a question about
 * the form rather than about the server.
 */
(function () {
  "use strict";

  /** Subjects that name a single asset, mirroring `models.ASSET_SUBJECTS`. */
  var ASSET_SUBJECTS = ["asa_price", "asa_total"];

  /** Subjects expressed as a percentage, mirroring `models.PERCENT_SUBJECTS`. */
  var PERCENT_SUBJECTS = ["total_percent"];

  /**
   * Show the fields this subject needs and hide the rest.
   *
   * **Both fields stay mounted.** Removing and re-adding them would lose what
   * the reader had typed when they looked at another subject and came back,
   * and would need a request to put them back.
   *
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
    return true;
  }

  /**
   * Whether this browser is an iPhone or an iPad.
   *
   * **Used only to choose the wording**, never to decide whether push works -
   * that is `supportState` below, and it asks the browser rather than reading
   * its name. A user agent is a claim; `PushManager` is a fact.
   *
   * iPadOS 13 and later report themselves as "Macintosh", so the touch points
   * are what tell an iPad from a Mac. `navigator.platform` would be the obvious
   * test and is deprecated.
   *
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
   *
   * **Feature detection first, and that is the whole design.** iOS Safari
   * exposes `PushManager` only to a site installed on the Home Screen, so its
   * absence is the same signal there as it is in any browser that cannot do
   * push at all - and asking the browser is right for every engine, including
   * ones nobody has thought to sniff for.
   *
   * The user agent is consulted afterwards, and only to pick a sentence: "add
   * this to your Home Screen" is something a reader can act on, and "this
   * browser cannot" is not.
   *
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
   *
   * **The copy is in the template, not here.** The script decides which
   * sentence is true; where sentences live is a question about editing them.
   *
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
   *
   * The key is published as base64url because it travels in JSON; the Push API
   * takes bytes. There is no browser helper for this, which is why every push
   * implementation carries these six lines.
   *
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
   * Ask permission, register the worker, subscribe, and tell the server.
   *
   * **Four things that can each say no**, and the reader is told which: the
   * browser may not support push, they may refuse the prompt, the worker may
   * fail to register, or our own endpoint may reject the subscription. A single
   * "something went wrong" would leave them with no idea whether to try again.
   *
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
          // **Not an error, and not retried.** A refusal is an answer, and a
          // browser will not prompt again anyway - so saying where to change it
          // is the only useful thing left.
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
    if (event.target.classList.contains("alerts-subject")) {
      // No `|| document` fallback: the select is rendered inside the panel, so
      // a miss is impossible - and `syncFields` already answers false for a
      // null root, which is the honest behaviour if it ever were.
      syncFields(event.target.closest(".alerts-panel"));
    }
  });

  /**
   * React to an htmx swap: open the modal that arrived, or re-sync a panel.
   *
   * **`event.target` is not the swapped content.** htmx 4 fires this on the
   * element that made the request - the *button* - and names the region it
   * replaced in `detail.ctx.target`. Reading `event.target` therefore searched
   * inside the button, found no dialog, and left the modal sitting in the
   * document unopened: a control that fetched everything correctly and looked
   * broken. The jest suite could not see it, because it calls `openModal`
   * directly; only a real browser fires a real htmx event.
   *
   * **Only these two swaps are acted on.** Other widgets swap fragments into
   * this same page all the time - live refresh does it every block - and
   * reopening the dialog on one of those would put the modal back in a
   * reader's face after they closed it.
   *
   * @param {Event} event - htmx's after-swap event.
   * @returns {boolean} whether this swap was one of ours.
   */
  function handleSwap(event) {
    var ctx = event.detail && event.detail.ctx;
    var swapped = (ctx && ctx.target) || event.target;
    if (!swapped || !swapped.querySelector) return false;

    if (swapped.querySelector("#alerts-modal")) {
      openModal(swapped);
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
      syncFields(document.querySelector(".alerts-panel") || swapped);
      return true;
    }
    return false;
  }

  /**
   * Move the alerts toolbar into the page's action row, beside Dust Sweep.
   *
   * **It renders where the partial lands, which is not where it belongs.**
   * `_swap_entry.html` arrives near the top of the page, so without this the
   * button sits in a strip of its own above the heading while Sweep dust - which
   * does exactly this - is down in the row with Historic data and CSV export.
   * Two controls of the same kind, in two different places.
   *
   * The same slot the sweep uses, and appended after it, so the order is stable
   * rather than a race between two scripts.
   *
   * @returns {boolean} whether the toolbar was moved.
   */
  function placeToolbar() {
    var toolbar = document.getElementById("id-alerts");
    var slot = document.getElementById("id-dustsweep-slot");
    if (!toolbar || !slot || slot === toolbar.parentNode) return false;
    slot.appendChild(toolbar);
    return true;
  }

  /**
   * Record the asset a reader picked out of the search results.
   *
   * **The hidden field is what the form posts**, so nothing is chosen until
   * this runs: a reader who types "USDC" and presses Add without picking a row
   * submits no asset, and the form tells them to choose one. Typing is not
   * choosing, and an id guessed from a partial match would be the wrong asset
   * rather than no asset.
   *
   * @param {Element} row - the clicked result row.
   * @returns {boolean} whether an asset was recorded.
   */
  function chooseAsset(row) {
    var field = row.closest(".alerts-asset-field");
    if (!field) return false;
    var hidden = field.querySelector(".alerts-asset-id");
    var chosen = field.querySelector(".alerts-asset-chosen");
    var results = field.querySelector(".alerts-asset-results");
    if (!hidden) return false;

    hidden.value = row.getAttribute("data-id") || "";
    if (chosen) {
      chosen.textContent =
        (row.getAttribute("data-unit") || "") + " #" + hidden.value;
    }
    // Cleared so the list does not sit open over the rest of the form; the
    // choice is now shown beside the box instead.
    if (results) results.innerHTML = "";
    return true;
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest) return;
    // Scoped to this widget's own results: the swap window renders the same
    // rows from the same endpoint, and its picker has its own handler.
    var row = event.target.closest(".alerts-asset-results .id-swap-asset-option");
    if (row) chooseAsset(row);
  });

  placeToolbar();

  // The partial itself arrives by swap, so the toolbar may not exist yet when
  // this script first runs - the same reason `handleSwap` exists at all.
  document.body.addEventListener("htmx:after:swap", placeToolbar);

  document.body.addEventListener("htmx:after:swap", handleSwap);

  // **Published so the page can tell this script is listening.**
  //
  // The tag that loads this file rides in `_swap_entry.html`, which is itself
  // swapped in - so it is fetched asynchronously, and for a moment the control
  // is on the page while nothing is listening for the swap it triggers. A press
  // in that window fetches the modal and leaves it closed, which is a reader
  // pressing a button that does nothing.
  //
  // The same shape as `window.asastatsWallet` and `window.asastatsSwap`, and
  // read for the same reason: something that arrives late has to say when it
  // has arrived.
  window.asastatsAlerts = {
    handleSwap: handleSwap,
    placeToolbar: placeToolbar,
    chooseAsset: chooseAsset,
    openModal: openModal,
    syncFields: syncFields,
  };

  /* istanbul ignore next -- exported for the jest suite only */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      syncFields: syncFields,
      handleSwap: handleSwap,
      placeToolbar: placeToolbar,
      chooseAsset: chooseAsset,
      openModal: openModal,
      supportState: supportState,
      showSupport: showSupport,
      isApplePortable: isApplePortable,
      isInstalled: isInstalled,
      enablePush: enablePush,
      vapidKeyBytes: vapidKeyBytes,
    };
  }
})();
