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

  // htmx 4 spelling. The modal arrives by swap, and so does every re-rendered
  // panel after a create or a delete, so both need the fields re-synced.
  // No `event.target || document` fallback and no `querySelector &&` guard: a
  // dispatched event always carries a target, and htmx fires this on the
  // element it swapped, so both would be branches no test could reach. An
  // unreachable guard is worse than none - it reads as a case somebody once
  // saw.
  document.body.addEventListener("htmx:after:swap", function (event) {
    if (event.target.querySelector("#alerts-modal")) {
      openModal(event.target);
    } else {
      syncFields(event.target);
    }
  });

  /* istanbul ignore next -- exported for the jest suite only */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      syncFields: syncFields,
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
