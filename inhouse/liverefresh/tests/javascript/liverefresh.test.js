/**
 * @file Unit tests for the Real-time refresh poll.
 *
 * `liverefresh.js` is an IIFE that runs the moment it is loaded and can return
 * early three ways - no marker, no htmx, no swap target - so every scenario has
 * to build the page *before* requiring it, and `jest.resetModules()` between
 * them. `load()` below is that dance; nothing else in here should call
 * `require` directly.
 *
 * The browser tests in `functional_tests/test_liverefresh_page.py` cover what a
 * reader sees. These cover what they cannot: the tab going away, storage
 * throwing, an interval that must not be started twice, and the three ways this
 * file decides it has nothing to do.
 */

const MODULE = "../../static/liverefresh/liverefresh.js";

/**
 * jsdom puts `localStorage` on the window as an **own** property, so replacing
 * it and then deleting it does not uncover the original - it removes it, and
 * every later test in the file dies on a bare `localStorage` reference. The
 * descriptor is captured once here and put back after each test.
 */
const STORAGE = Object.getOwnPropertyDescriptor(window, "localStorage");

const POLL_URL = "/widgets/liverefresh/HASH";
/** What the poll actually asks for: the URL plus what the page was built from. */
const POLLED = `${POLL_URL}?holdings=beef1234`;

/**
 * Put a page on screen for the module to find.
 *
 * @param {Object} [options]
 * @param {boolean} [options.marker] render the per-reader marker
 * @param {boolean} [options.band] render the out-of-band swap target
 * @param {string} [options.interval] `data-interval`, omitted when null
 * @param {string} [options.grace] `data-grace`, omitted when null
 * @param {string} [options.holdings] `data-holdings` on the band's carrier,
 *   omitted when null - what the page was rendered from
 * @param {string} [options.bandId] which layout's band to render: the dynamic
 *   layout's `id-band-total` or the classic layout's `id-band-classic`
 * @param {boolean} [options.badge] render the allowance badge
 * @param {boolean} [options.control] render the toolbar's refresh control
 */
function page(options = {}) {
  const {
    marker = true,
    band = true,
    interval = "3",
    grace = "300",
    holdings = "beef1234",
    bandId = "id-band-total",
    badge = true,
    control = true,
  } = options;
  const parts = [];
  if (band) {
    parts.push(
      "<h1" +
        (holdings === null ? "" : ` data-holdings="${holdings}"`) +
        `><span id="${bandId}">1,881.51 ALGO</span></h1>`
    );
  }
  if (marker) {
    parts.push(
      `<span id="id-liverefresh" data-poll-url="${POLL_URL}"` +
        (interval === null ? "" : ` data-interval="${interval}"`) +
        (grace === null ? "" : ` data-grace="${grace}"`) +
        "></span>"
    );
  }
  parts.push('<div id="id-liverefresh-spent" hidden></div>');
  // The badge and the control it gets moved next to. Both ship in the markup -
  // the badge in the non-cached partial, the control in the toolbar - so a test
  // page without them is testing a page that cannot exist.
  if (control) {
    parts.push('<div id="tb-wrap"><button id="tb-refresh"></button></div>');
  }
  if (badge) {
    parts.push('<span id="id-liverefresh-left" hidden></span>');
  }
  document.body.innerHTML = parts.join("");
}

/**
 * Listeners added by every module instance loaded in this file, so they can be
 * taken off again.
 *
 * **`jest.resetModules()` gives a fresh module and the same `document`.** Each
 * load attaches its own `visibilitychange` listener, and without this every
 * previously loaded instance still answers the event - with its own closure,
 * its own timer, and a call into whatever `window.htmx` currently is. A test
 * expecting one poll on return sees one per load so far, which reads as the
 * code polling too often rather than as the harness leaking.
 */
let attached = [];

/** Load the module against the current page, and return what it exported. */
function load({ htmx = true } = {}) {
  if (htmx) {
    window.htmx = { ajax: jest.fn() };
  } else {
    delete window.htmx;
  }
  jest.resetModules();
  const spy = jest
    .spyOn(document, "addEventListener")
    .mockImplementation((type, listener, options) => {
      attached.push([type, listener]);
      Document.prototype.addEventListener.call(document, type, listener, options);
    });
  try {
    return require(MODULE);
  } finally {
    spy.mockRestore();
  }
}

/** Point `document.visibilityState` at `state` for the rest of the test. */
function visibility(state) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  });
}

beforeEach(() => {
  jest.useFakeTimers();
  localStorage.clear();
  visibility("visible");
  page();
});

afterEach(() => {
  attached.forEach(([type, listener]) =>
    document.removeEventListener(type, listener)
  );
  attached = [];
  Object.defineProperty(window, "localStorage", STORAGE);
  jest.clearAllTimers();
  jest.useRealTimers();
});

describe("deciding there is nothing to do", () => {
  it("does nothing without the per-reader marker", () => {
    // The ordinary case: the marker renders only for a subscriber who opted
    // in, so on most page loads this file is present and idle.
    page({ marker: false });

    const module = load();

    jest.advanceTimersByTime(60000);
    expect(window.htmx.ajax).not.toHaveBeenCalled();
    expect(module).toEqual({});
  });

  it("does nothing without htmx", () => {
    // It cannot apply a response on its own, and asking for one it will drop
    // still costs the engine a re-price of this page on every block.
    const module = load({ htmx: false });

    jest.advanceTimersByTime(60000);
    expect(module).toEqual({});
  });

  it("does nothing when the page has no swap target", () => {
    // The legacy layout renders the same figures without the ids the
    // out-of-band swaps address. Polling there applies nothing while still
    // holding an `lvx` subscription - work with no possible effect.
    page({ band: false });

    const module = load();

    jest.advanceTimersByTime(60000);
    expect(window.htmx.ajax).not.toHaveBeenCalled();
    expect(module).toEqual({});
  });
});

describe("the interval", () => {
  it("polls once a block while the reader has it armed", () => {
    localStorage.setItem("refresh", "y");
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
    expect(window.htmx.ajax).toHaveBeenCalledWith(
      "GET",
      POLLED,
      expect.objectContaining({ swap: "none" })
    );
  });

  it("tells the server what the page was rendered from", () => {
    // **The half the fragments cannot do.** An out-of-band swap needs a row
    // that is already on the page, so an asset just bought has nowhere to
    // arrive and one just sold is never mentioned. The server answers that with
    // a reload instead - and it can only know to when it is told what the
    // reader is actually looking at.
    localStorage.setItem("refresh", "y");
    page({ holdings: "cafe5678" });
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledWith(
      "GET",
      `${POLL_URL}?holdings=cafe5678`,
      expect.anything()
    );
  });

  it("keeps a poll URL that already has a query string intact", () => {
    localStorage.setItem("refresh", "y");
    page();
    document
      .getElementById("id-liverefresh")
      .setAttribute("data-poll-url", `${POLL_URL}?x=1`);
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledWith(
      "GET",
      `${POLL_URL}?x=1&holdings=beef1234`,
      expect.anything()
    );
  });

  it("polls without it when the page carries no fingerprint", () => {
    // A page rendered before this existed, and the legacy layout. Neither can
    // be reloaded on a signal it never sends, and both keep working exactly as
    // they did: fragments, and nothing else.
    localStorage.setItem("refresh", "y");
    page({ holdings: null });
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledWith(
      "GET",
      POLL_URL,
      expect.anything()
    );
  });

  it("polls on the classic layout too", () => {
    // The classic band is a different element with a different id. Guarding on
    // the dynamic one alone is what kept this layout from ever polling - which
    // was correct while there was nothing to swap there, and is not now.
    localStorage.setItem("refresh", "y");
    page({ bandId: "id-band-classic" });
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("asks for nothing while the reader has it off", () => {
    // The interval still runs: this file does not own the control and must not
    // guess at its events, so it reads the key every time rather than being
    // told. The cost of being wrong here is one storage read a few seconds.
    load();

    jest.advanceTimersByTime(30000);

    expect(window.htmx.ajax).not.toHaveBeenCalled();
  });

  it("notices the reader arming it without any event", () => {
    load();
    jest.advanceTimersByTime(3000);
    expect(window.htmx.ajax).not.toHaveBeenCalled();

    localStorage.setItem("refresh", "y");
    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("falls back to sane numbers when the marker carries none", () => {
    // `parseInt` of undefined is NaN, and a NaN interval is an interval that
    // never fires - so the fallback is what stands between a missing attribute
    // and a feature that is silently dead.
    page({ interval: null, grace: null });
    localStorage.setItem("refresh", "y");
    load();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("does not start a second interval over the first", () => {
    // `start` is called on load and again whenever a hidden tab returns. Two
    // intervals would double every reader's request rate and the engine's work
    // with it, and nothing about the page would look wrong.
    localStorage.setItem("refresh", "y");
    const module = load();

    module.start();
    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("tolerates being stopped twice", () => {
    const module = load();

    module.stop();
    module.stop();

    expect(() => jest.advanceTimersByTime(3000)).not.toThrow();
  });
});

describe("reading the checkbox", () => {
  it("treats unreadable storage as off", () => {
    // Private mode, or storage blocked by policy. The checkbox cannot be read,
    // so the page is left exactly as the server rendered it rather than the
    // poll throwing once every interval forever.
    load();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage is blocked");
      },
    });

    expect(() => jest.advanceTimersByTime(30000)).not.toThrow();
    expect(window.htmx.ajax).not.toHaveBeenCalled();
  });

  it("reads the key both layouts agree on", () => {
    localStorage.setItem("refresh", "y");
    const module = load();

    expect(module.armed()).toBe(true);

    localStorage.setItem("refresh", "");

    expect(module.armed()).toBe(false);
  });
});

describe("following the tab out of view and back", () => {
  it("stops polling once hidden longer than the grace period", () => {
    // Every polling tab holds a subscription the engine re-prices every block.
    // A tab nobody has looked at for five minutes is the clearest case of work
    // with no reader.
    localStorage.setItem("refresh", "y");
    load();

    visibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    jest.advanceTimersByTime(301000);
    window.htmx.ajax.mockClear();
    jest.advanceTimersByTime(30000);

    expect(window.htmx.ajax).not.toHaveBeenCalled();
  });

  it("keeps polling while hidden inside the grace period", () => {
    // Switching tabs for a moment must not cost a catch-up render on the way
    // back, so the poll carries on for a while rather than stopping at once.
    localStorage.setItem("refresh", "y");
    load();

    visibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    window.htmx.ajax.mockClear();
    jest.advanceTimersByTime(9000);

    expect(window.htmx.ajax).toHaveBeenCalled();
  });

  it("polls immediately on return rather than waiting out the interval", () => {
    // The page is up to the grace period behind. Waiting another interval to
    // say so is the difference between a live page and one that looks broken
    // for three seconds every time it is looked at.
    localStorage.setItem("refresh", "y");
    load();

    visibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    jest.advanceTimersByTime(301000);
    window.htmx.ajax.mockClear();

    visibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("restarts the interval that the grace period stopped", () => {
    localStorage.setItem("refresh", "y");
    load();

    visibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    jest.advanceTimersByTime(301000);
    visibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    window.htmx.ajax.mockClear();

    jest.advanceTimersByTime(3000);

    expect(window.htmx.ajax).toHaveBeenCalledTimes(1);
  });

  it("does not start polling for a reader who returns with it off", () => {
    load();

    visibility("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    visibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    jest.advanceTimersByTime(30000);

    expect(window.htmx.ajax).not.toHaveBeenCalled();
  });
});

describe("the daily allowance running out", () => {
  it("stops polling and hands the page back to the free timer", () => {
    // **The handover is the point.** A page that simply stopped would leave the
    // reader with neither the live updates nor the 60-second reload a
    // non-subscriber gets - worse than never having had it, and
    // indistinguishable from the feature being broken. `address.js` stands its
    // own timer down whenever the marker is present and asks every tick, so
    // removing the marker is the whole handover.
    localStorage.setItem("refresh", "y");
    const module = load();

    module.spent();
    jest.advanceTimersByTime(30000);

    expect(window.htmx.ajax).not.toHaveBeenCalled();
    expect(document.getElementById("id-liverefresh")).toBeNull();
  });

  it("says so rather than going quiet", () => {
    const loaded = load();

    loaded.spent();

    expect(document.getElementById("id-liverefresh-spent").hidden).toBe(false);
  });

  it("is safe to run twice", () => {
    // htmx fires the trigger on every response carrying the header, and a
    // reader whose allowance ran out mid-flight can have one already in the
    // air. The second call finds the marker detached.
    const module = load();

    module.spent();

    expect(() => module.spent()).not.toThrow();
  });

  it("survives a page with no badge to clear", () => {
    // `spent` hides the allowance badge as well as revealing the notice, and
    // the badge is the newer of the two - so a template that has the notice and
    // not the badge is exactly the shape a half-finished edit leaves behind. It
    // must not throw on every poll of every reader who ran out.
    page({ badge: false });
    const module = load();

    expect(() => module.spent()).not.toThrow();
    expect(document.getElementById("id-liverefresh-spent").hidden).toBe(false);
  });

  it("survives a page with no notice to reveal", () => {
    // The notice lives in the same non-cached partial as the marker, so it is
    // always there together with it - but a template edit that dropped one must
    // not throw on every poll of every reader who ran out.
    page();
    document.getElementById("id-liverefresh-spent").remove();
    const module = load();

    expect(() => module.spent()).not.toThrow();
  });
});

describe("showing what is left of the allowance", () => {
  /** Fire the event the server sends on every poll response. */
  function left(module, seconds) {
    module.showLeft({ detail: { seconds } });
  }

  it("moves the badge next to the control it belongs to", () => {
    // **The badge ships in the non-cached partial, not the toolbar.** The
    // address page is cached across readers, so a balance rendered into it
    // would show whoever warmed the entry to everybody else - the same trap the
    // Dust Sweep button hit. Rendering it per-reader and relocating it is what
    // keeps the figure private while letting it read as part of the toolbar.
    localStorage.setItem("refresh", "y");
    const module = load();

    left(module, 7200);

    const badge = document.getElementById("id-liverefresh-left");
    expect(badge.parentNode.id).toBe("tb-wrap");
    expect(badge.previousElementSibling.id).toBe("tb-refresh");
  });

  it("reads as an allowance rather than a stopwatch", () => {
    localStorage.setItem("refresh", "y");
    const module = load();

    left(module, 7080);

    expect(document.getElementById("id-liverefresh-left").textContent).toBe(
      "1h 58m left"
    );
  });

  it("formats whole hours, minutes and the last stretch", () => {
    const module = load();

    expect(module.humanize(7200)).toBe("2h");
    expect(module.humanize(7080)).toBe("1h 58m");
    expect(module.humanize(600)).toBe("10 min");
    expect(module.humanize(59)).toBe("under a minute");
    expect(module.humanize(0)).toBe("under a minute");
  });

  it("stays hidden while the control is off", () => {
    // A figure sitting there while nothing is being spent invites the reader to
    // watch it not move, and it is not being spent: what is not polled is not
    // charged.
    localStorage.removeItem("refresh");
    const module = load();

    left(module, 3600);

    expect(document.getElementById("id-liverefresh-left").hidden).toBe(true);
  });

  it("goes away when the allowance runs out", () => {
    localStorage.setItem("refresh", "y");
    const module = load();
    left(module, 60);

    module.spent();

    expect(document.getElementById("id-liverefresh-left").hidden).toBe(true);
  });

  it("ignores a response carrying no usable figure", () => {
    // Unmetered tiers get no header at all, and a malformed one must not write
    // "NaN left" beside the control.
    localStorage.setItem("refresh", "y");
    const module = load();

    expect(() => module.showLeft({})).not.toThrow();
    expect(() => left(module, "soon")).not.toThrow();
    expect(document.getElementById("id-liverefresh-left").textContent).toBe("");
  });

  it("survives a page with no badge to fill", () => {
    // A template edit that dropped it must not throw on every poll.
    page({ badge: false });
    const module = load();

    expect(() => left(module, 3600)).not.toThrow();
  });

  it("leaves the badge where it is when there is no control", () => {
    // The classic layout has no `tb-refresh`; the figure still belongs on the
    // page, just not relocated.
    page({ control: false });
    localStorage.setItem("refresh", "y");
    const module = load();

    left(module, 3600);

    expect(document.getElementById("id-liverefresh-left").hidden).toBe(false);
  });
});

describe("settling a position fragment", () => {
  /** A position row as the page renders it, with an open breakdown.
   *
   * Appended to a real page: the module returns early without its marker, so
   * a body holding only a position would export nothing to call.
   */
  function position(pid, { value = "4.5", expandedNow = "true" } = {}) {
    page();
    document.body.innerHTML +=
      '<div class="position" data-value="' + value + '">' +
      '  <div class="position-val">' +
      '    <button id="pv-' + pid + '" class="amt tdist val" data-val="' + value +
      '" aria-expanded="' + expandedNow + '">4.50</button>' +
      "  </div>" +
      "</div>";
    return document.getElementById("pv-" + pid);
  }

  /** Replace the element the way htmx does, then fire the pair around it.
   *
   * **htmx 4's shape, which is per response rather than per element.**
   * `htmx:before:swap` carries the whole task list, each task naming the
   * element still in the document that is about to be replaced;
   * `htmx:after:swap` fires once, after every one of them is in.
   */
  function swap(subject, module, pid, newValue) {
    module.rememberExpanded({ detail: { tasks: [{ target: subject }] } });
    const fresh = document.createElement("button");
    fresh.id = subject.id;
    fresh.className = subject.className;
    fresh.setAttribute("data-val", newValue);
    fresh.setAttribute("aria-expanded", "false"); // what the server renders
    subject.replaceWith(fresh);
    module.settlePosition({ detail: {} });
    return fresh;
  }

  test("an open breakdown is still open afterwards", () => {
    // `dynamic.js` owns aria-expanded and the `.dist` panel is a sibling, so
    // it survives the swap. Without this the control claims closed over a
    // panel that is still showing.
    const subject = position("p1-5-abc");

    const module = load();
    const fresh = swap(subject, module, "p1-5-abc", "9.0");

    expect(fresh.getAttribute("aria-expanded")).toBe("true");
  });

  test("the position's own total follows its new value", () => {
    // `toolbar.js` sums `data-value` off `.position` for every category total
    // and for the allocation band. A fragment cannot reach an attribute
    // without replacing the element holding it, so this carries it up - or
    // the page's headline drifts away from its own rows.
    const subject = position("p1-5-abc", { value: "4.5" });

    const module = load();
    swap(subject, module, "p1-5-abc", "9.0");

    expect(
      document.querySelector(".position").getAttribute("data-value")
    ).toBe("9.0");
  });

  test("a closed breakdown stays closed", () => {
    const subject = position("p1-5-abc", { expandedNow: "false" });

    const module = load();
    const fresh = swap(subject, module, "p1-5-abc", "9.0");

    expect(fresh.getAttribute("aria-expanded")).toBe("false");
  });

  test("an event carrying no tasks is ignored by both halves", () => {
    // A malformed or synthetic event must not take the poll down with it: both
    // handlers run inside the response, so a throw here stops the swaps.
    const module = load();

    expect(() => module.rememberExpanded({})).not.toThrow();
    expect(() => module.rememberExpanded({ detail: {} })).not.toThrow();
    expect(() => module.rememberExpanded({ detail: { tasks: [] } })).not.toThrow();
    expect(() =>
      module.rememberExpanded({ detail: { tasks: [{}, null] } })
    ).not.toThrow();
    expect(() => module.settlePosition({})).not.toThrow();
    expect(() => module.settlePosition({ detail: {} })).not.toThrow();
  });

  test("a fragment nobody remembered keeps what the server sent", () => {
    // `htmx:before:swap` not having named this id. Under htmx 4 that cannot
    // happen for a real swap - a task exists only where a target was found -
    // so this is the defensive case: there is nothing to restore, and
    // inventing a value would close a breakdown the reader had open.
    page();
    const module = load();
    document.body.innerHTML +=
      '<div class="position" data-value="4.5">' +
      '<button id="pv-p1-5-fresh" data-val="9.0" aria-expanded="true"></button>' +
      "</div>";

    module.settlePosition({ detail: {} });

    expect(
      document.getElementById("pv-p1-5-fresh").getAttribute("aria-expanded")
    ).toBe("true");
  });

  test("a position value with no row around it is left alone", () => {
    // Defensive: the id says position, the DOM disagrees. Nothing to carry the
    // value up to, and a throw would stop every swap after it in the response.
    page();
    const module = load();
    document.body.innerHTML +=
      '<button id="pv-p1-5-orphan" data-val="9.0"></button>';
    const orphan = document.getElementById("pv-p1-5-orphan");
    module.rememberExpanded({ detail: { tasks: [{ target: orphan }] } });

    expect(() => module.settlePosition({ detail: {} })).not.toThrow();
  });

  test("a fragment whose element has left the document is ignored", () => {
    // The lookup is by id because htmx replaces the node, so the element named
    // by the task is the old one. If the replacement never arrived there is
    // nothing to settle - and the id must still be forgotten, or it would be
    // retried against the next response.
    page();
    const module = load();
    const gone = document.createElement("button");
    gone.id = "pv-p1-5-missing";
    module.rememberExpanded({ detail: { tasks: [{ target: gone }] } });

    expect(() => module.settlePosition({ detail: {} })).not.toThrow();
    // Forgotten: a second settle with nothing swapped must also be a no-op.
    expect(() => module.settlePosition({ detail: {} })).not.toThrow();
  });

  test("a value of nothing settles as zero rather than as absent", () => {
    // `data-value` is summed, so an empty attribute would make the category
    // total `NaN` and take the whole allocation band with it.
    page();
    const module = load();
    document.body.innerHTML +=
      '<div class="position" data-value="4.5">' +
      '<button id="pv-p1-5-blank"></button></div>';
    const blank = document.getElementById("pv-p1-5-blank");
    module.rememberExpanded({ detail: { tasks: [{ target: blank }] } });

    module.settlePosition({ detail: {} });

    expect(
      document.querySelector(".position").getAttribute("data-value")
    ).toBe("0");
  });

  test("anything that is not a position value is left alone", () => {
    // The same events carry the band and every row figure. Reaching for a
    // `.position` from one of those would write a row's value into whatever
    // ancestor happened to match.
    page();
    const module = load();
    document.body.innerHTML +=
      '<div class="position" data-value="4.5">' +
      '<span id="v31566704" data-val="9.0">9.00</span></div>';
    const row = document.getElementById("v31566704");

    module.rememberExpanded({ detail: { tasks: [{ target: row }] } });
    module.settlePosition({ detail: {} });

    expect(
      document.querySelector(".position").getAttribute("data-value")
    ).toBe("4.5");
  });

  test("a key inherited from Object.prototype is not treated as a row", () => {
    // `for...in` walks the prototype chain, so any library that writes an
    // enumerable property onto `Object.prototype` - older polyfills and
    // analytics shims still do - would have this loop visit a key nobody put
    // in `expanded`. If that key happened to name a real element, its row's
    // `data-value` would be rewritten from a figure this response never sent,
    // and `toolbar.js` would total it.
    //
    // The `hasOwnProperty` guard is what stops it, and this is the only way to
    // exercise that branch: nothing else can put an inherited key there.
    page();
    const module = load();
    const intruder = "pv-p1-5-inherited";
    Object.defineProperty(Object.prototype, intruder, {
      value: "true",
      enumerable: true,
      configurable: true,
      writable: true,
    });
    try {
      document.body.innerHTML +=
        '<div class="position" data-value="4.5">' +
        '<button id="' + intruder + '" data-val="9.0"></button></div>';

      module.settlePosition({ detail: {} });

      // Untouched. Without the guard this would read "9.0".
      expect(
        document.querySelector(".position").getAttribute("data-value")
      ).toBe("4.5");
    } finally {
      delete Object.prototype[intruder];
    }
  });
});
