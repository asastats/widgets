/**
 * @file Unit tests for the processed-time localizer.
 *
 * `local-time.js` is an IIFE that rewrites every `time[data-local-time]` the
 * moment it is loaded and again after each htmx swap, so every scenario builds
 * the page *before* requiring it, with `jest.resetModules()` between them.
 * `load()` below is that dance.
 *
 * The browser test in `functional_tests/test_pnl_widget.py` covers what a
 * reader sees in a real timezone. These cover the unreadable timestamp, the
 * swap listener and the formatting options.
 */

const MODULE = "../../static/pnl/local-time.js";

/** 9 Oct 2025, 08:53:20 UTC, as the view's `processed_iso` renders it. */
const ISO = "2025-10-09T08:53:20Z";
const FALLBACK = "9 Oct 2025, 08:53 UTC";

/**
 * Put a page with `<time>` elements on screen, then run the module.
 *
 * @param {string[]} [stamps] the `datetime` attribute of each element
 */
function load(stamps = [ISO]) {
  document.body.innerHTML = stamps
    .map((stamp) => `<time datetime="${stamp}" data-local-time>${FALLBACK}</time>`)
    .join("");
  jest.resetModules();
  require(MODULE);
}

describe("local-time", () => {
  let format;

  beforeEach(() => {
    format = jest
      .spyOn(Date.prototype, "toLocaleString")
      .mockReturnValue("Oct 9, 2025, 5:53 PM GMT+9");
  });

  afterEach(() => {
    format.mockRestore();
    document.body.innerHTML = "";
  });

  test("replaces the UTC text with the reader's local time on load", () => {
    load();
    expect(document.querySelector("time").textContent).toBe(
      "Oct 9, 2025, 5:53 PM GMT+9",
    );
  });

  test("formats in the browser's own locale, with the zone shown", () => {
    load();
    expect(format).toHaveBeenCalledWith(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  });

  test("localizes every element", () => {
    load([ISO, "2025-10-10T10:00:00Z"]);
    const texts = [...document.querySelectorAll("time")].map((t) => t.textContent);
    expect(texts).toEqual(["Oct 9, 2025, 5:53 PM GMT+9", "Oct 9, 2025, 5:53 PM GMT+9"]);
  });

  test("keeps the server's text when the timestamp is unreadable", () => {
    load(["not a date"]);
    expect(format).not.toHaveBeenCalled();
    expect(document.querySelector("time").textContent).toBe(FALLBACK);
  });

  test("ignores a time element without the marker", () => {
    document.body.innerHTML = `<time datetime="${ISO}">plain</time>`;
    jest.resetModules();
    require(MODULE);
    expect(document.querySelector("time").textContent).toBe("plain");
  });

  test("localizes a fragment that htmx swaps in afterwards", () => {
    load([]);
    expect(format).not.toHaveBeenCalled();
    document.body.insertAdjacentHTML(
      "beforeend",
      `<time datetime="${ISO}" data-local-time>${FALLBACK}</time>`,
    );
    document.body.dispatchEvent(new Event("htmx:after:swap"));
    expect(document.querySelector("time").textContent).toBe(
      "Oct 9, 2025, 5:53 PM GMT+9",
    );
  });
});
