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
 */
function page(options = {}) {
  const {
    marker = true,
    band = true,
    interval = "3",
    grace = "300",
    holdings = "beef1234",
  } = options;
  const parts = [];
  if (band) {
    parts.push(
      "<h1" +
        (holdings === null ? "" : ` data-holdings="${holdings}"`) +
        '><span id="id-band-total">1,881.51 ALGO</span></h1>'
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
