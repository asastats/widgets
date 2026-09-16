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
