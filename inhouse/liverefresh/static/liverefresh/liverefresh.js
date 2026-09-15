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
  if (!document.getElementById("id-band-total")) {
    return;
  }

  var url = marker.dataset.pollUrl;
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
  document.addEventListener("visibilitychange", visibility);
  start();

  /* istanbul ignore next -- exported for the jest suite only */
  if (typeof exports !== "undefined") {
    module.exports = { poll, start, stop, visibility, armed };
  }
})();
