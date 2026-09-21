/**
 * @file Real-time refresh: poll the engine's published block for this page.
 * @author Ivica Paleka
 */

/*
 * The subscriber half of the "Auto-refresh" checkbox.
 *
 * The free half reloads the page. This does not: it asks for the fragments the
 * block changed and lets htmx swap them out of band, so scroll position, open
 * sections and filters all survive. That is the whole reason the idle guard the
 * free half needs does not apply here - nothing is thrown out from under the
 * reader, so there is nothing to wait for them to stop doing.
 *
 * **The poll is also the subscription.** Serving it is what tells the engine
 * this page is being read; there is no subscribe and no unsubscribe to keep in
 * step with a reader who closed the tab. They stop polling, the heartbeat
 * expires, and the engine stops re-pricing the page.
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

  var url = marker.dataset.pollUrl;
  // **What this page was rendered from**, so the server can tell a price move
  // from a holdings change. The out-of-band swaps can only reach rows the page
  // already has, so an asset bought or sold is not something the fragments can
  // express at all - the server answers that with a reload instead, and it can
  // only know to when it is told what the reader is actually looking at.
  //
  // Read from the page rather than remembered per reader: a change between the
  // render and the first poll would otherwise never be noticed.
  //
  // Read once. A reload replaces the document, so the value cannot go stale
  // without this script starting again.
  var carrier = document.querySelector("[data-holdings]");
  var holdings = carrier ? carrier.dataset.holdings : "";
  if (holdings) {
    url += (url.indexOf("?") === -1 ? "?" : "&") +
      "holdings=" + encodeURIComponent(holdings);
  }
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
   *
   * `swap: "none"` because there is nothing to put where the request came
   * from: every fragment in the response carries `hx-swap-oob` and lands
   * wherever it belongs on the page. A 204 - which is most blocks, for most
   * pages - leaves the DOM untouched.
   */
  function poll() {
    if (!armed()) {
      return;
    }
    // **Hidden past the grace period stops the poll entirely**, rather than
    // polling on quietly. Every polling tab holds a subscription the engine
    // re-prices on every block, and a tab nobody has looked at for five
    // minutes is the clearest case of work with no reader.
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
   *
   * Coming back always polls once before resuming the interval: the page is up
   * to `grace` plus one interval behind, and waiting another interval to say so
   * is the difference between a live page and one that looks broken for three
   * seconds every time it is looked at.
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
   *
   * **Handing back to the free timer is the point.** A page that simply stopped
   * would leave the reader with neither the live updates nor the 60-second
   * reload a non-subscriber gets, which is worse than never having had it - and
   * indistinguishable from the feature being broken.
   *
   * `address.js` stands its own timer down whenever `#id-liverefresh` is on the
   * page, and asks every tick rather than once, so removing the marker is the
   * whole handover. No coordination between the two scripts beyond that.
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
   *
   * **The badge ships in the non-cached partial and is moved here.** The
   * address page is `cache_page`d across readers, so a balance rendered into it
   * would show whoever warmed the entry to everybody else - the same trap the
   * Dust Sweep button hit. Rendering it per-reader and relocating it keeps the
   * figure private while letting it read as part of the toolbar.
   *
   * Hidden again once the control is disarmed: a number that keeps sitting
   * there while nothing is being spent invites the reader to watch it not move.
   *
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
   *
   * Minutes below an hour and whole hours above it: a badge counting seconds
   * down beside a page that updates every block is two things moving for no
   * reason, and the number is an allowance rather than a stopwatch.
   *
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

  // **The interval runs regardless; `poll` decides whether to ask.**
  //
  // Binding to the control was the obvious thing and it was wrong. The two
  // layouts arm this differently - design 1 has a checkbox that fires `change`,
  // the dynamic toolbar has a `<button>` that fires `click` - so a listener for
  // either one works on exactly one of the two pages, silently. A widget that
  // does not own the control should not be guessing at its events.
  //
  // What both layouts do agree on is the `refresh` key, so that is the only
  // thing read. The cost of asking every interval while disarmed is one
  // `localStorage` read every few seconds and no request at all.
  /**
   * Finish what a position fragment cannot say on its own.
   *
   * **Two things travel with a position's value and neither is inside the
   * element being replaced.**
   *
   * `aria-expanded` is live state: `dynamic.js` toggles it, and the `.dist`
   * panel it controls is a *sibling*, so the panel survives a swap that resets
   * the control. Without this a reader watching an open breakdown would see the
   * button claim closed over a panel still showing.
   *
   * `data-value` sits on the `.position` itself and is what `toolbar.js` sums
   * for every category total and for the allocation band. A fragment cannot
   * reach an attribute without replacing the element holding it, so the page's
   * headline arithmetic would drift away from its own rows - the exact failure
   * that made narrowing the reload a mistake in the first place.
   *
   * **Once per response, not once per element.** htmx 2 bracketed every
   * out-of-band element with `htmx:oobBeforeSwap`/`oobAfterSwap` and this ran
   * per element. htmx 4 has neither event: `htmx:before:swap` carries the whole
   * task list before anything is swapped, and `htmx:after:swap` fires once all
   * of them are in - so the same work is two passes rather than 2N events.
   *
   * Both still fire before the whole-response event `toolbar.js` repaints on,
   * which is the ordering that has to survive the port. Doing it later would
   * repaint from the figures this is here to correct.
   *
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
  // Sent with every poll response, including the 204s, so the figure does not
  // sit still on a quiet page and then jump.
  document.body.addEventListener("liverefresh:left", showLeft);
  // Bracketing the response's whole task list. These fire on the poll's source
  // element - the marker - and bubble, which is why listening on `body` reaches
  // them.
  //
  // **`true` is the capture phase, and it is load-bearing.** Under htmx 2 this
  // ran on `oobAfterSwap`, which fired during the swap and so always preceded
  // the whole-response event `toolbar.js` repaints on. In htmx 4 both are
  // `htmx:after:swap`, and bubble-phase listeners run in registration order -
  // which puts `toolbar.js` first, because it is loaded with the page while
  // this arrives later inside the swapped `_swap_entry.html` partial.
  //
  // That order is the bug this whole mechanism exists to prevent: the toolbar
  // would recompute every category total and the allocation band from the
  // `data-value` attributes *before* the line below corrects them. Capturing on
  // an ancestor runs before any bubble listener on it, whatever registered
  // first, so the ordering no longer depends on which script loaded when.
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
    };
  }
})();
