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
  if (!marker || !window.htmx) {
    return;
  }
  // **Nothing to swap, nothing to ask for.** The band partials live in the
  // dynamic layout; the legacy one renders the same figures without the ids
  // the out-of-band swaps address. Polling there would apply nothing while
  // still holding an `lvx` subscription, which costs the engine a re-price of
  // this page every block for a reader who would see no difference.
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
    if (!armed()) {
      return;
    }
    // Hidden past grace period stops poll entirely.
    if (hiddenAt && Date.now() - hiddenAt > grace) {
      stop();
      return;
    }
    window.htmx.ajax("GET", url, { source: marker, swap: "none" });
  }

  function start() {
    if (timer === null) {
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
   * The day's free watching is gone.
   * Hands back to free timer; removing marker is whole handover.
   */
  function spent() {
    stop();
    var badge = document.getElementById("id-liverefresh-left");
    if (badge) {
      badge.hidden = true;
    }
    var notice = document.getElementById("id-liverefresh-spent");
    if (notice) {
      notice.hidden = false;
    }
    if (marker.parentNode) {
      marker.parentNode.removeChild(marker);
    }
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
    var control = document.getElementById("tb-refresh");
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

// Interval runs regardless; poll decides whether to ask. Control binding was wrong.
  /**
   * Finish what a position fragment cannot say on its own.
   * aria-expanded and data-value travel with position value.
   * Once per response; capture phase for ordering.
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
  }

  /**
   * @param {Element} element - a swapped element.
   * @returns {boolean} whether it is a position's value.
   */
  function isPositionValue(element) {
    return !!(element.id && element.id.indexOf("pv-") === 0);
  }

  document.addEventListener("visibilitychange", visibility);
  // Fired by the server through `HX-Trigger` when the allowance runs out.
  document.body.addEventListener("liverefresh:spent", spent);
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

  // Sent with every poll response, including the 204s, so the figure does not
  // sit still on a quiet page and then jump.
  document.body.addEventListener("liverefresh:left", showLeft);
  // The positions moved and the assets did not, so one venue group is
  // showLeft: every poll response; regroup: positions moved, assets same.
  document.body.addEventListener("liverefresh:left", showLeft);
  document.body.addEventListener("liverefresh:regroup", regroup);
  document.body.addEventListener("liverefresh:regrouped", regrouped);
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
      humanize,
      rememberExpanded,
      settlePosition,
      regroup,
      regrouped,
      withHoldings,
    };
  }
})();
