/**
 * @file Real-time refresh: poll the engine's published block for this page.
 * @author Ivica Paleka
 *
 * Subscriber half of Auto-refresh: htmx OOB swaps preserve scroll/state.
 * Poll is the subscription; grace period stops hidden tabs.
 */

(function () {
  /** The per-reader marker, delivered by the page's non-cached partial. */
  var marker = document.getElementById("id-liverefresh");
  /**
   * `aria-expanded` per position value id, carried across its own swap.
   *
   * Keyed by id and cleared as each one settles, so a fragment that never
   * arrives cannot leave a stale answer for the next one.
  */
  var expanded = {};
  var classicValueAttributes = {};
  if (!marker || !window.htmx) {
    return;
  }
  // **Nothing to swap, nothing to ask for.** Both layouts carry a live band
  // target; a page with neither is one the swaps cannot reach.
  //
  // Asked of the page rather than told by the server, so that a layout gaining
  // the partials starts working without anything else being changed - and one
  // losing them stops, rather than quietly polling into the void.
  //
  // Either layout's band counts. The dynamic one renders `#id-band-total` and
  // the classic one `#id-band-classic`; a reader is on one or the other, and a
  // page with neither is one the swaps cannot reach.
  if (
    !document.getElementById("id-band-total") &&
    !document.getElementById("id-band-classic")
  ) {
    return;
  }

  var pollUrl = marker.dataset.pollUrl;
  // Page's rendered holdings fingerprint; regroup updates it.
  var carrier = document.querySelector("[data-holdings]");
  var holdings = carrier ? carrier.dataset.holdings : "";

  /**
   * Return `base` carrying `value` as its `holdings` parameter.
   *
   * @param {string} base - the poll URL as the marker supplied it.
   * @param {string} value - the fingerprint the page is carrying.
   * @returns {string}
   */
  function withHoldings(base, value) {
    if (!value) {
      return base;
    }
    return (
      base +
      (base.indexOf("?") === -1 ? "?" : "&") +
      "holdings=" +
      encodeURIComponent(value)
    );
  }

  var url = withHoldings(pollUrl, holdings);
  /** The last payload `seq` this tab applied; the server folds in what it missed. */
  var since = null;
  /** Names this tab's carry and last total on the server, apart from other tabs. */
  var tab = Math.random().toString(36).slice(2, 10) || "t";

  /**
   * Return `base` carrying this tab's id, and `since` once it has applied a payload.
   *
   * @param {string} base - the poll URL with its holdings.
   * @returns {string}
   */
  function withSince(base) {
    var query = "tab=" + tab + (since === null ? "" : "&since=" + since);
    return base + (base.indexOf("?") === -1 ? "?" : "&") + query;
  }
  /** Whether a regroup is in flight; the trigger arrives faster than it. */
  var regrouping = false;
  var interval = (parseInt(marker.dataset.interval, 10) || 3) * 1000;
  var grace = (parseInt(marker.dataset.grace, 10) || 300) * 1000;
  var timer = null;
  /** When the tab was hidden, or 0 while it is visible. */
  var hiddenAt = 0;

  /** Whether the reader has the Auto-refresh checkbox on. */
  function armed() {
    try {
      return (localStorage.getItem("refresh") || "") === "y";
    } catch (error) {
      // Private mode, or storage blocked. The checkbox cannot be read, so the
      // page is left exactly as the server rendered it.
      return false;
    }
  }

  /**
   * Ask for this block's fragments.
   * swap: "none" - fragments carry hx-swap-oob; 204 leaves DOM untouched.
   */
  function poll() {
    syncLog();
    if (!armed()) {
      return;
    }
    // Hidden past grace period stops poll entirely.
    if (hiddenAt && Date.now() - hiddenAt > grace) {
      stop();
      return;
    }
    window.htmx.ajax("GET", withSince(url), { source: marker, swap: "none" });
  }

  /**
   * Remember which payload the response just delivered.
   * @param {CustomEvent} event carrying `{ seq }`
   */
  function caughtUp(event) {
    var seq = event && event.detail && event.detail.seq;
    if (typeof seq === "number") {
      since = seq;
    }
  }

  /**
   * Reveal the live log, moving it once to where its layout puts it.
   *
   * Dynamic: beside the charts panel, in a row. Classic: a right-aligned
   * section below the consolidated box, `#id-cons`. Moving a DOM node keeps its
   * listeners, so the charts' bindings survive the move.
   */
  function showLog() {
    var log = document.getElementById("id-livelog");
    if (!log) {
      return;
    }
    if (!log.parentNode.classList.contains("charts-row") &&
        !log.parentNode.classList.contains("livelog-section")) {
      var charts = document.getElementById("charts");
      var cons = document.getElementById("id-cons");
      if (charts) {
        var row = document.createElement("div");
        row.className = "charts-row";
        charts.parentNode.insertBefore(row, charts);
        row.appendChild(charts);
        row.appendChild(log);
      } else if (cons) {
        var section = document.createElement("div");
        section.className = "livelog-section";
        cons.parentNode.insertBefore(section, cons.nextSibling);
        section.appendChild(log);
      } else {
        return;
      }
    }
    log.hidden = false;
    restoreLog();
    watchLog(log);
  }

  /** Most rows the log keeps in the page. Older ones are dropped from the end. */
  var LOG_ROW_CAP = 200;
  /** Rows that arrived while the log was closed, cleared when it is opened. */
  var unread = 0;
  var logWatch = null;
  var logRestored = false;

  /**
   * Save log rows to sessionStorage keyed by pollUrl.
   * Saves inner HTML, className, and data-key to preserve everything on restore.
   * @returns {void}
   */
  function saveLog() {
    try {
      var list = document.getElementById("id-livelog-list");
      if (!list) return;
      var rows = [];
      Array.prototype.forEach.call(list.querySelectorAll(".livelog-row"), function (row) {
        rows.push({
          html: row.innerHTML,
          className: row.className,
          key: row.getAttribute("data-key")
        });
      });
      sessionStorage.setItem("livelog:" + pollUrl, JSON.stringify(rows));
    } catch (error) {
      // sessionStorage might be unavailable or full; silently continue.
    }
  }

  /**
   * Restore the live log from sessionStorage once per page load, deduplicating by key.
   * Builds a set of existing keys from server-rendered rows, then appends only
   * saved rows that don't already exist.
   * @returns {void}
   */
  function restoreLog() {
    if (logRestored) return;
    logRestored = true;
    try {
      var list = document.getElementById("id-livelog-list");
      if (!list) return;
      var saved = sessionStorage.getItem("livelog:" + pollUrl);
      if (!saved) return;
      var rows = JSON.parse(saved);
      if (!Array.isArray(rows)) return;

      // Build set of existing keys from server-rendered rows
      var existingKeys = {};
      Array.prototype.forEach.call(list.querySelectorAll(".livelog-row"), function (row) {
        existingKeys[row.getAttribute("data-key")] = true;
      });

      // Append saved rows that don't duplicate existing keys
      rows.forEach(function (row) {
        // Skip if key exists (duplicate)
        if (row.key && existingKeys[row.key]) return;

        // Restore the row with saved className (preserves livelog-gap)
        var newLi = document.createElement("li");
        newLi.className = row.className;
        newLi.innerHTML = row.html;
        newLi.setAttribute("data-key", row.key || "");
        existingKeys[row.key] = true;
        list.appendChild(newLi);
      });
    } catch (error) {
      // JSON parse or sessionStorage error; silently continue.
    }
  }

  function showUnread() {
    var badge = document.getElementById("id-livelog-unread");
    if (!badge) {
      return;
    }
    badge.textContent = unread + " new";
    badge.hidden = unread === 0;
  }

  /**
   * Count rows that arrive while the log is closed, and keep the list short.
   *
   * Attached once, when the watch starts. Rows restored on load are already in
   * the list by then, so they are not counted as new.
   */
  function watchLog(log) {
    var list = document.getElementById("id-livelog-list");
    if (logWatch || list === null || typeof MutationObserver === "undefined") {
      return;
    }
    logWatch = new MutationObserver(function (records) {
      var added = 0;
      records.forEach(function (record) {
        Array.prototype.forEach.call(record.addedNodes, function (node) {
          if (node.nodeType === 1 && node.classList.contains("livelog-row")) {
            // Check if this row duplicates an existing key
            var key = node.getAttribute("data-key");
            if (key) {
              // Count how many rows already have this key
              var existingWithKey = 0;
              Array.prototype.forEach.call(list.querySelectorAll(".livelog-row[data-key='" + key.replace(/'/g, "\\'") + "']"), function (row) {
                if (row !== node) existingWithKey += 1;
              });
              // Only count as new if this is the first row with this key
              if (existingWithKey === 0) added += 1;
            } else {
              // Gap rows (no key) are always counted as new
              added += 1;
            }
          }
        });
      });
      if (added && !log.open) {
        unread += added;
        showUnread();
      }
      while (list.children.length > LOG_ROW_CAP) {
        list.removeChild(list.lastElementChild);
      }
      saveLog();
    });
    logWatch.observe(list, { childList: true });
    log.addEventListener("toggle", function () {
      if (log.open) {
        unread = 0;
        showUnread();
      }
    });
  }

  function hideLog() {
    var log = document.getElementById("id-livelog");
    if (log) {
      log.hidden = true;
    }
  }

  /**
   * Show the live log while the reader has Auto-refresh on, hide it otherwise.
   *
   * Run on every tick rather than once at load, because the checkbox can be
   * turned on after the page has loaded and nothing else would reveal the log.
   */
  function syncLog() {
    if (armed()) {
      showLog();
    } else {
      hideLog();
    }
  }

  function start() {
    syncLog();
    if (timer === null) {
      // The interval runs regardless; `poll` decides whether to ask, by reading
      // the `refresh` key. Never bind to the control: design 1's checkbox fires
      // `change` and the dynamic toolbar's button fires `click`, so a listener
      // for either works on exactly one page, silently.
      timer = window.setInterval(poll, interval);
    }
  }

  function stop() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  /**
   * Follow the tab in and out of view.
   * Coming back polls once before resuming.
   */
  function visibility() {
    if (document.visibilityState === "hidden") {
      hiddenAt = Date.now();
      return;
    }
    hiddenAt = 0;
    if (armed()) {
      poll();
      start();
    }
  }

  /**
   * Give the page back to `address.js`'s sixty-second reload.
   * Removing the marker is the whole handover: that is what it reads.
   */
  function refreshTitle() {
    var live = !!(marker && marker.parentNode && marker.dataset.pollUrl);
    var text = live
      ? "Refresh this page in real time"
      : "Reload this page about once a minute, waiting for a pause if you are reading";
    var control = document.getElementById("tb-refresh") || document.querySelector(".refresh label");
    if (control) control.setAttribute("title", text);
  }

  function handBack() {
    stop();
    hideLog();
    var badge = document.getElementById("id-liverefresh-left");
    if (badge) {
      badge.hidden = true;
    }
    if (marker.parentNode) {
      marker.parentNode.removeChild(marker);
    }
    refreshTitle();
  }

  /**
   * The day's free watching is gone. Says so, then hands back.
   */
  function spent() {
    var notice = document.getElementById("id-liverefresh-spent");
    if (notice) {
      notice.hidden = false;
    }
    handBack();
  }

  /**
   * A refusal the next poll cannot fix. Hands back, silently.
   *
   * **4xx only.** A refused request stays refused however often it is repeated -
   * an unlinked address polled 767 times in 85 minutes, and every one wrote a
   * 35-line traceback. A 5xx is the opposite: a worker recycling answers 502 for
   * a second, and standing down for that would cost the reader live refresh
   * until they reloaded. See docs/logbook.md.
   *
   * Scoped by `event.target`: htmx dispatches this on the element that issued
   * the request, so a 4xx from the swap, the sweep or alerts is not ours.
   *
   * @param {CustomEvent} event carrying `{ ctx }`
   */
  function refused(event) {
    if (event.target !== marker) {
      return;
    }
    // Read straight through, no `|| {}` guards: htmx assigns `ctx.response`
    // *before* it dispatches this event, so a missing one is not an input
    // production can produce - and a guard for it would be a branch no test
    // could reach honestly.
    var status = Number(event.detail.ctx.response.status);
    if (!(status >= 400 && status < 500)) {
      return;
    }
    handBack();
  }

  /**
   * Show what is left of the allowance, beside the control it belongs to.
   * Badge from non-cached partial, moved here for privacy.
   * @param {CustomEvent} event carrying `{ seconds }`
   */
  function showLeft(event) {
    var badge = document.getElementById("id-liverefresh-left");
    if (!badge) {
      return;
    }
    var detail = (event && event.detail) || {};
    var seconds = Number(detail.seconds);
    if (!isFinite(seconds)) {
      return;
    }
    // `#tb-refresh` is the dynamic toolbar's, `.refresh label` is classic's -
    // and classic is the only layout a reader below Intro can be on, so looking
    // for the toolbar alone left the badge at the top of the page for exactly
    // the readers whose allowance it describes. See docs/logbook.md.
    var control =
      document.getElementById("tb-refresh") ||
      document.querySelector(".refresh label");
    if (control && badge.parentNode !== control.parentNode) {
      control.parentNode.insertBefore(badge, control.nextSibling);
    }
    badge.textContent = humanize(seconds) + " left";
    badge.hidden = !armed();
  }

  /**
   * Return a compact duration a reader can read at a glance.
   * Minutes < hour, whole hours >= hour; allowance not stopwatch.
   * @param {number} seconds
   * @returns {string}
   */
  function humanize(seconds) {
    if (seconds < 60) {
      return "under a minute";
    }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
      return minutes + " min";
    }
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    return rest ? hours + "h " + rest + "m" : hours + "h";
  }

  /**
   * Finish what a position fragment cannot say on its own.
   * aria-expanded and data-value travel with position value.
   * Once per response, and in the capture phase: both must run before the
   * whole-response event `toolbar.js` repaints on, or it sums the figures this
   * is here to correct.
   * @param {Event} event - htmx's `htmx:before:swap`, carrying `detail.tasks`.
   */
  function rememberExpanded(event) {
    // `task.target` is the element *currently in the document* that is about to
    // be replaced, which is the only moment its live `aria-expanded` can be
    // read. Afterwards it is detached, and htmx 4 redirects an event away from
    // a detached element to `document` - so there is no second chance at it.
    var tasks = (event.detail && event.detail.tasks) || [];
    for (var index = 0; index < tasks.length; index += 1) {
      var target = tasks[index] && tasks[index].target;
      if (target && isPositionValue(target)) {
        expanded[target.id] = target.getAttribute("aria-expanded");
      }
      if (target && isClassicValue(target)) {
        classicValueAttributes[target.id] = {
          className: target.className,
          distid: target.getAttribute("data-distid"),
        };
      }
    }
  }

  /**
   * @param {Event} event - htmx's `htmx:after:swap`. Its detail is not read:
   *   `expanded` already names every row this response touched.
   */
  function settlePosition(event) {
    for (var id in expanded) {
      if (!Object.prototype.hasOwnProperty.call(expanded, id)) continue;
      // htmx replaced the node, so read the one now in the document.
      var element = document.getElementById(id);
      if (element && isPositionValue(element)) {
        var was = expanded[id];
        if (was !== null && was !== undefined) {
          element.setAttribute("aria-expanded", was);
        }
        var position = element.closest && element.closest(".position");
        if (position) {
          position.setAttribute(
            "data-value",
            element.getAttribute("data-val") || "0"
          );
        }
      }
      // Cleared whether or not it was found, so a fragment that never landed
      // cannot leave a stale answer behind for the next response.
      delete expanded[id];
    }
    for (var classicId in classicValueAttributes) {
      if (!Object.prototype.hasOwnProperty.call(classicValueAttributes, classicId)) continue;
      var classic = document.getElementById(classicId);
      var attributes = classicValueAttributes[classicId];
      if (classic) {
        classic.className = attributes.className;
        if (attributes.distid === null) classic.removeAttribute("data-distid");
        else classic.setAttribute("data-distid", attributes.distid);
      }
      delete classicValueAttributes[classicId];
    }
  }

  /**
   * @param {Element} element - a swapped element.
   * @returns {boolean} whether it is a position's value.
   */
  function isPositionValue(element) {
    return !!(element.id && element.id.indexOf("pv-") === 0);
  }

  function isClassicValue(element) {
    return !!(element.id && element.id.indexOf("ppv-") === 0);
  }

  document.addEventListener("visibilitychange", visibility);
  // Fired by the server through `HX-Trigger` when the allowance runs out.
  document.body.addEventListener("liverefresh:spent", spent);
  // `htmx:response:error`, not `htmx:responseError`: this build is htmx 4 and
  // the v1/v2 name does not exist, so a listener for it would never fire.
  document.body.addEventListener("htmx:response:error", refused);
  /**
   * Send what the page is carrying, so the server can say what changed.
   * Position changes need server to diff; sends asset:pid tokens.
   * One at a time to avoid stacking.
   */
  function regroup() {
    if (regrouping || !window.htmx) {
      return;
    }
    var rows = document.querySelectorAll(".position[data-pid][data-owner]");
    var pids = [];
    Array.prototype.forEach.call(rows, function (row) {
      // `data-owner` is `f<asset id>`; the `f` is the asset card's element id
      // prefix and is not part of the id itself.
      pids.push(row.dataset.owner.replace(/^f/, "") + ":" + row.dataset.pid);
    });
    regrouping = true;
    window.htmx.ajax("POST", pollUrl + "/regroup", {
      source: marker,
      swap: "none",
      values: { pids: pids.join(" ") },
      // CSRF sent explicitly: only POST, from span not form.
      headers: { "X-CSRFToken": csrfToken() },
    });
  }

  /**
   * Return Django's CSRF cookie, or "" when the page carries none.
   *
   * @returns {string}
   */
  function csrfToken() {
    var match = document.cookie.match(/(^|;)\s*csrftoken\s*=\s*([^;]+)/);
    return match ? match[2] : "";
  }

  /**
   * Take the new groups, and put the reader's view back around them.
   * Group-by-venue: toolbar moves pgroup; drop old copies.
   * Updates holdings fingerprint to avoid re-regroup loop.
   * @param {CustomEvent} event carrying `{ holdings }`
   */
  function regrouped(event) {
    regrouping = false;
    var detail = (event && event.detail) || {};
    if (detail.holdings) {
      // Fingerprint page has now caught up to; avoids re-regroup loop.
      holdings = detail.holdings;
      url = withHoldings(pollUrl, holdings);
      var carrier = document.querySelector("[data-holdings]");
      if (carrier) {
        carrier.dataset.holdings = holdings;
      }
    }
    var toolbar = window.asastatsToolbar;
    if (!toolbar || typeof toolbar.regroup !== "function") {
      return;
    }
    var venues = document.getElementById("venue-list");
    if (venues) {
      // Old copy of group page now has twice.
      Array.prototype.slice
        .call(venues.querySelectorAll(".pgroup"))
        .filter(function (group) {
          var home = group._asastatsHome && group._asastatsHome.parent;
          return home && !home.isConnected;
        })
        .forEach(function (group) {
          group.parentNode.removeChild(group);
        });
    }
    toolbar.regroup();
  }

  // showLeft: every poll response, including the 204s, so the figure does not
  // sit still on a quiet page and then jump. regroup: the positions moved and
  // the assets did not, so one venue group is re-rendered instead of a reload.
  document.body.addEventListener("liverefresh:left", showLeft);
  document.body.addEventListener("liverefresh:regroup", regroup);
  document.body.addEventListener("liverefresh:regrouped", regrouped);
  document.body.addEventListener("liverefresh:seq", caughtUp);

  // Re-apply currency/total-no-NFT formatting after OOB swaps
  // (wireFetchedItems may not catch swap:"none" responses)
  document.body.addEventListener("htmx:after:swap", function() {
    if (typeof restoreDisplayChoices === "function") {
      restoreDisplayChoices();
    }
  });

  refreshTitle();
  // Bracketing task list; capture phase for ordering before toolbar.js.
  document.body.addEventListener("htmx:before:swap", rememberExpanded, true);
  document.body.addEventListener("htmx:after:swap", settlePosition, true);
  start();

  /* istanbul ignore next -- exported for the jest suite only */
  if (typeof exports !== "undefined") {
    module.exports = {
      poll,
      start,
      stop,
      visibility,
      armed,
      spent,
      showLeft,
      refused,
      handBack,
      humanize,
      rememberExpanded,
      settlePosition,
      regroup,
      regrouped,
      withHoldings,
    };
  }
})();
