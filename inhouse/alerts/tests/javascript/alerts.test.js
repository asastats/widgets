/**
 * The two things `alerts.js` is for, and nothing else.
 *
 * Everything that can be htmx is htmx: the modal is fetched by the control, and
 * creating or removing a rule swaps a panel the server re-rendered. What is
 * left for script is the part htmx has no opinion about - a native `<dialog>`
 * has to be opened by `showModal()`, and which fields a subject needs is a
 * question about the form rather than about the server.
 *
 * So these tests are about field visibility and dialog opening. There is no
 * rule-rendering to test, deliberately: the server draws the list.
 */

const alerts = require("../../static/alerts/alerts.js");

/** The panel as `_panel.html` renders it, both conditional fields mounted. */
function panel(subject) {
  document.body.innerHTML = `
    <div id="id-alerts-panel" class="alerts-panel">
      <form class="alerts-form">
        <select class="alerts-subject">
          <option value="asa_price">Asset price</option>
          <option value="asa_price_percent">Asset price, percentage move</option>
          <option value="asa_amount">How much of an asset I hold</option>
          <option value="asa_total">What my holding of an asset is worth</option>
          <option value="total_value">Portfolio total</option>
          <option value="total_percent">Portfolio total, percentage move</option>
        </select>
        <select class="alerts-direction">
          <option value="up" selected>Rises above</option>
          <option value="down">Falls below</option>
        </select>
        <div class="alerts-field alerts-asset-field" hidden>
          <input type="hidden" name="asset_id" class="alerts-asset-id">
          <input type="hidden" name="asset_unit" class="alerts-asset-unit">
          <button type="button" class="alerts-assetbtn id-alerts-assetbtn"
                  aria-expanded="false">
            <img class="alerts-assetbtn-icon" alt="" hidden>
            <span class="alerts-assetbtn-text">Choose asset</span>
          </button>
          <div class="alerts-picker" hidden>
            <input type="search" class="alerts-asset-search" name="q">
            <div class="alerts-asset-results"></div>
          </div>
        </div>
        <label class="alerts-field alerts-threshold-field">
          <input type="text" name="threshold" class="alerts-threshold">
          <span class="alerts-units">
            <button type="button" class="alerts-unit id-alerts-unit"
                    data-unit="algo" aria-pressed="true">ALGO</button>
            <button type="button" class="alerts-unit id-alerts-unit"
                    data-unit="usd" aria-pressed="false">USD</button>
          </span>
          <input type="hidden" name="threshold_unit" class="alerts-unit-value"
                 value="algo">
          <small class="alerts-now" data-current-total="1000"
                 data-algo-per-usd="4"></small>
        </label>
        <label class="alerts-field alerts-window-field" hidden>
          <select name="window_seconds"><option value="3600">1 hour</option></select>
          <small class="alerts-window-note">warm-up</small>
        </label>
      </form>
    </div>`;
  document.querySelector(".alerts-subject").value = subject;
  return document.querySelector(".alerts-panel");
}

const assetField = () => document.querySelector(".alerts-asset-field");
const windowField = () => document.querySelector(".alerts-window-field");

describe("which fields a subject needs", () => {
  test("an asset price rule asks for an asset and not a window", () => {
    alerts.syncFields(panel("asa_price"));

    expect(assetField().hidden).toBe(false);
    expect(windowField().hidden).toBe(true);
  });

  test("a holding rule asks for an asset too", () => {
    alerts.syncFields(panel("asa_total"));

    expect(assetField().hidden).toBe(false);
  });

  test("a portfolio total asks for neither", () => {
    alerts.syncFields(panel("total_value"));

    expect(assetField().hidden).toBe(true);
    expect(windowField().hidden).toBe(true);
  });

  test("an asset percentage asks for both, and for no unit", () => {
    // **The only subject that needs an asset *and* a window**, which is the
    // combination neither of the two arrays alone would produce. It is also a
    // percentage, so the ALGO/USD control has nothing to say: a "5" here means
    // five per cent whichever button is lit, and leaving the control up would
    // invite the reader to believe otherwise.
    const root = panel("asa_price_percent");
    alerts.syncFields(root);

    expect(assetField().hidden).toBe(false);
    expect(windowField().hidden).toBe(false);
    expect(root.querySelector(".alerts-units").hidden).toBe(true);
  });

  test("a percentage move asks for a window and not an asset", () => {
    // **The one subject that needs a period**, because only a percentage is
    // measured over one - and only it meets the thin-asset problem.
    alerts.syncFields(panel("total_percent"));

    expect(windowField().hidden).toBe(false);
    expect(assetField().hidden).toBe(true);
  });

  test("switching subject moves the fields rather than reloading", () => {
    // Both stay mounted, so what a reader typed survives a look at another
    // subject. Removing and re-adding them would lose it, and would need a
    // request to put them back.
    const root = panel("asa_price");
    alerts.syncFields(root);
    const input = assetField().querySelector("input");
    input.value = "393537671";

    document.querySelector(".alerts-subject").value = "total_value";
    alerts.syncFields(root);
    document.querySelector(".alerts-subject").value = "asa_price";
    alerts.syncFields(root);

    expect(assetField().querySelector("input").value).toBe("393537671");
  });

  test("a panel with no form is left alone rather than throwing", () => {
    // The unentitled branch of the modal renders an upgrade message and no
    // form at all, and this runs on every swap.
    document.body.innerHTML = '<div class="alerts-panel"><p>Upgrade</p></div>';

    expect(alerts.syncFields(document.querySelector(".alerts-panel"))).toBe(false);
  });

  test("no root at all is survivable", () => {
    expect(alerts.syncFields(null)).toBe(false);
  });

  test("a form with no subject select is survivable", () => {
    document.body.innerHTML =
      '<div class="alerts-panel"><form class="alerts-form"></form></div>';

    expect(alerts.syncFields(document.querySelector(".alerts-panel"))).toBe(false);
  });
});

describe("opening the dialog", () => {
  /** jsdom implements <dialog> without showModal in some versions. */
  function dialog(withShowModal = true) {
    document.body.innerHTML = '<dialog id="alerts-modal"></dialog>';
    const element = document.getElementById("alerts-modal");
    if (withShowModal) {
      element.showModal = jest.fn(() => {
        element.open = true;
      });
    } else {
      element.showModal = undefined;
    }
    return element;
  }

  test("the modal is opened once it has been swapped in", () => {
    const element = dialog();

    expect(alerts.openModal(document)).toBe(true);
    expect(element.showModal).toHaveBeenCalled();
  });

  test("an already open dialog is not opened twice", () => {
    // `showModal()` on an open dialog throws in a real browser, which would
    // take the swap handler down with it.
    const element = dialog();
    element.open = true;

    alerts.openModal(document);

    expect(element.showModal).not.toHaveBeenCalled();
  });

  test("a page with no modal is survivable", () => {
    document.body.innerHTML = "<div></div>";

    expect(alerts.openModal(document)).toBe(false);
  });

  test("a browser without showModal is survivable", () => {
    dialog(false);

    expect(alerts.openModal(document)).toBe(false);
  });

  test("no root falls back to the document", () => {
    dialog();

    expect(alerts.openModal(null)).toBe(true);
  });
});

describe("the listeners the module binds", () => {
  test("the close button closes an open dialog", () => {
    document.body.innerHTML =
      '<dialog id="alerts-modal"><button class="id-alerts-close">x</button></dialog>';
    const element = document.getElementById("alerts-modal");
    element.open = true;
    element.close = jest.fn();

    document.querySelector(".id-alerts-close").click();

    expect(element.close).toHaveBeenCalled();
  });

  test("the close button does nothing when the dialog is already shut", () => {
    // `close()` on a shut dialog is harmless, but asking first keeps the
    // handler honest about what it is for.
    document.body.innerHTML =
      '<dialog id="alerts-modal"><button class="id-alerts-close">x</button></dialog>';
    const element = document.getElementById("alerts-modal");
    element.open = false;
    element.close = jest.fn();

    document.querySelector(".id-alerts-close").click();

    expect(element.close).not.toHaveBeenCalled();
  });

  test("a click elsewhere is ignored", () => {
    document.body.innerHTML = '<div><button id="other">x</button></div>';

    expect(() => document.getElementById("other").click()).not.toThrow();
  });

  test("changing the subject re-syncs the fields", () => {
    // The delegated path, which is what actually runs for a reader - the
    // direct `syncFields` tests above never prove the wiring.
    panel("asa_price");
    const select = document.querySelector(".alerts-subject");
    select.value = "total_percent";

    select.dispatchEvent(new window.Event("change", { bubbles: true }));

    expect(windowField().hidden).toBe(false);
    expect(assetField().hidden).toBe(true);
  });

  test("a change on something else is ignored", () => {
    document.body.innerHTML = '<input id="unrelated">';

    expect(() =>
      document
        .getElementById("unrelated")
        .dispatchEvent(new window.Event("change", { bubbles: true }))
    ).not.toThrow();
  });

  test("a swap carrying the modal opens it", () => {
    document.body.innerHTML = '<div id="slot"><dialog id="alerts-modal"></dialog></div>';
    const element = document.getElementById("alerts-modal");
    element.showModal = jest.fn(() => {
      element.open = true;
    });

    document
      .getElementById("slot")
      .dispatchEvent(new window.CustomEvent("htmx:after:swap", { bubbles: true }));

    expect(element.showModal).toHaveBeenCalled();
  });

  test("a swap carrying only the panel re-syncs without opening", () => {
    // Every create and delete swaps the panel back, and the subject the reader
    // had chosen has to keep its fields showing.
    const root = panel("total_percent");

    root.dispatchEvent(
      new window.CustomEvent("htmx:after:swap", { bubbles: true })
    );

    expect(windowField().hidden).toBe(false);
  });
});

describe("a form missing the conditional fields", () => {
  test("is adjusted without throwing", () => {
    // Defensive: the two fields are rendered by `_panel.html` for every
    // subject, so this shape does not occur today. It is guarded because the
    // handler runs on every swap, and a throw here would stop the swap that
    // carried the reader's new rule - losing the thing they just asked for.
    document.body.innerHTML = `
      <div class="alerts-panel">
        <form class="alerts-form">
          <select class="alerts-subject">
            <option value="asa_price">Asset price</option>
          </select>
        </form>
      </div>`;

    expect(alerts.syncFields(document.querySelector(".alerts-panel"))).toBe(true);
  });
});

describe("telling the reader whether alerts can reach them", () => {
  const realUA = navigator.userAgent;

  /** Set up a browser: push present or not, which UA, installed or not. */
  function browser({ push = false, ua = "Mozilla/5.0 (X11; Linux x86_64)",
                     touchPoints = 0, standalone = undefined,
                     displayMode = false } = {}) {
    if (push) {
      window.PushManager = function () {};
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: {},
      });
    } else {
      delete window.PushManager;
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: undefined,
      });
    }
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: ua,
    });
    Object.defineProperty(navigator, "maxTouchPoints", {
      configurable: true,
      value: touchPoints,
    });
    Object.defineProperty(navigator, "standalone", {
      configurable: true,
      value: standalone,
    });
    window.matchMedia = jest.fn(() => ({ matches: displayMode }));
  }

  afterEach(() => {
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: realUA,
    });
    delete window.PushManager;
  });

  const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)";
  const IPAD13 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)";

  test("a browser with push is told nothing", () => {
    browser({ push: true });

    expect(alerts.supportState()).toBe("ok");
  });

  test("an iPhone in a tab is told to add it to the Home Screen", () => {
    // **The case this whole thing exists for.** iOS Safari exposes PushManager
    // only to an installed site, so a reader who enables alerts in a tab would
    // otherwise receive nothing and never learn why.
    browser({ push: false, ua: IPHONE });

    expect(alerts.supportState()).toBe("ios-install");
  });

  test("an installed iPhone without push is told its iOS is too old", () => {
    // Installed and still no PushManager means older than 16.4 - a different
    // sentence, because there is nothing left to install.
    browser({ push: false, ua: IPHONE, standalone: true });

    expect(alerts.supportState()).toBe("ios-old");
  });

  test("display-mode standalone counts as installed", () => {
    // `navigator.standalone` is Safari's; the media query is the standard one.
    browser({ push: false, ua: IPHONE, displayMode: true });

    expect(alerts.supportState()).toBe("ios-old");
  });

  test("an iPad reporting itself as a Mac is still an iPad", () => {
    // iPadOS 13+ says "Macintosh". Touch points are what tell them apart, and
    // `navigator.platform` - the obvious test - is deprecated.
    browser({ push: false, ua: IPAD13, touchPoints: 5 });

    expect(alerts.supportState()).toBe("ios-install");
  });

  test("a real Mac without push is not told about the Home Screen", () => {
    // Same user agent string as the iPad above, no touch points. Advice about
    // adding to a Home Screen would be nonsense on a desktop.
    browser({ push: false, ua: IPAD13, touchPoints: 0 });

    expect(alerts.supportState()).toBe("unsupported");
  });

  test("a browser without push and without a match media is survivable", () => {
    browser({ push: false, ua: IPHONE });
    window.matchMedia = undefined;

    expect(alerts.supportState()).toBe("ios-install");
  });

  test("only the sentence that applies is shown", () => {
    document.body.innerHTML = `
      <dialog id="alerts-modal">
        <p data-support="ios-install" hidden>a</p>
        <p data-support="ios-old" hidden>b</p>
        <p data-support="unsupported" hidden>c</p>
      </dialog>`;
    browser({ push: false, ua: IPHONE });

    expect(alerts.showSupport(document)).toBe("ios-install");
    const shown = Array.from(document.querySelectorAll("[data-support]"))
      .filter((p) => !p.hidden)
      .map((p) => p.getAttribute("data-support"));
    expect(shown).toEqual(["ios-install"]);
  });

  test("a browser with push is shown none of them", () => {
    document.body.innerHTML = `
      <dialog id="alerts-modal">
        <p data-support="ios-install" hidden>a</p>
        <p data-support="unsupported" hidden>c</p>
      </dialog>`;
    browser({ push: true });

    alerts.showSupport(document);

    expect(
      Array.from(document.querySelectorAll("[data-support]")).every((p) => p.hidden)
    ).toBe(true);
  });

  test("opening the modal decides it", () => {
    document.body.innerHTML = `
      <dialog id="alerts-modal">
        <p data-support="unsupported" hidden>c</p>
      </dialog>`;
    const element = document.getElementById("alerts-modal");
    element.showModal = jest.fn(() => {
      element.open = true;
    });
    browser({ push: false });

    alerts.openModal(document);

    expect(document.querySelector('[data-support="unsupported"]').hidden).toBe(false);
  });
});

describe("showSupport with no root", () => {
  test("falls back to the document", () => {
    // Exported, so a caller may reasonably pass nothing - unlike the internal
    // fallbacks removed elsewhere in this file, this one is reachable.
    document.body.innerHTML = '<p data-support="unsupported" hidden>c</p>';
    delete window.PushManager;
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    });

    expect(alerts.showSupport()).toBe("unsupported");
    expect(document.querySelector("[data-support]").hidden).toBe(false);
  });
});

describe("turning notifications on", () => {
  /** The `.alerts-enable` block as the modal renders it. */
  function enableBlock() {
    document.body.innerHTML = `
      <div class="alerts-enable"
           data-vapid-key="BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U"
           data-subscribe-url="/widgets/alerts/subscribe"
           data-unsubscribe-url="/widgets/alerts/unsubscribe"
           data-worker-url="/alerts-service-worker.js">
        <button type="button" class="alerts-enable-btn id-alerts-enable">Notify</button>
        <span class="alerts-enable-state"></span>
      </div>`;
    return document.querySelector(".alerts-enable");
  }

  /** Make the browser look capable, and answer the prompt with `permission`. */
  function capable(permission = "granted", { subscribeFails = false } = {}) {
    window.PushManager = function () {};
    global.Notification = { requestPermission: jest.fn(() => Promise.resolve(permission)) };
    const subscription = { toJSON: () => ({ endpoint: "https://push.example/x" }) };
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        register: jest.fn(() =>
          Promise.resolve({
            pushManager: {
              subscribe: jest.fn(() =>
                subscribeFails
                  ? Promise.reject(new Error("no"))
                  : Promise.resolve(subscription)
              ),
            },
          })
        ),
      },
    });
    global.fetch = jest.fn(() => Promise.resolve({ ok: true }));
    global.atob = (s) => Buffer.from(s, "base64").toString("binary");
  }

  const state = () => document.querySelector(".alerts-enable-state").textContent;

  afterEach(() => {
    delete window.PushManager;
    delete global.Notification;
  });

  test("a granted prompt subscribes and tells the server", async () => {
    capable("granted");
    const root = enableBlock();

    await alerts.enablePush(root);

    expect(global.fetch).toHaveBeenCalledWith(
      "/widgets/alerts/subscribe",
      expect.objectContaining({ method: "POST" })
    );
    expect(state()).toBe("This browser is on.");
  });

  test("a refused prompt says where to change it, and does not retry", async () => {
    // **Not an error.** A refusal is an answer, and the browser will not prompt
    // again - so the only useful thing left is saying where the setting is.
    capable("denied");
    const root = enableBlock();

    await alerts.enablePush(root);

    expect(state()).toMatch(/blocked/i);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("a browser without push never prompts", async () => {
    // The notice above the button already explains which case this is, so the
    // button must not add a prompt the browser would ignore anyway.
    delete window.PushManager;
    global.Notification = { requestPermission: jest.fn() };
    const root = enableBlock();

    await alerts.enablePush(root);

    expect(global.Notification.requestPermission).not.toHaveBeenCalled();
    expect(state()).toMatch(/not available/i);
  });

  test("a server that refuses the subscription says so", async () => {
    capable("granted");
    global.fetch = jest.fn(() => Promise.resolve({ ok: false }));
    const root = enableBlock();

    await alerts.enablePush(root);

    expect(state()).toMatch(/refused/i);
  });

  test("a failure anywhere in the chain is reported, not swallowed", async () => {
    // Four things can each say no; a single "something went wrong" would leave
    // the reader with no idea whether trying again is worth it.
    capable("granted", { subscribeFails: true });
    const root = enableBlock();

    await alerts.enablePush(root);

    expect(state()).toBe("no");
  });

  test("the button is wired, not merely callable", async () => {
    capable("granted");
    enableBlock();

    document.querySelector(".id-alerts-enable").click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(global.Notification.requestPermission).toHaveBeenCalled();
  });
});

describe("the VAPID key the Push API wants", () => {
  test("base64url becomes the right bytes", () => {
    // No browser helper does this, which is why every push implementation
    // carries it. `-` and `_` are base64url's substitutions, and the padding
    // has to be put back before decoding.
    global.atob = (s) => Buffer.from(s, "base64").toString("binary");

    const bytes = alerts.vapidKeyBytes("aGVsbG8");

    expect(Array.from(bytes)).toEqual([104, 101, 108, 108, 111]);
  });

  test("the url-safe characters are translated", () => {
    global.atob = (s) => Buffer.from(s, "base64").toString("binary");

    const plain = alerts.vapidKeyBytes("-_8");
    expect(Array.from(plain)).toEqual([251, 255]);
  });
});

describe("the edges of the enable flow", () => {
  function block({ withState = true } = {}) {
    document.body.innerHTML = `
      <div class="alerts-enable" data-vapid-key="aGVsbG8"
           data-subscribe-url="/s" data-worker-url="/w">
        <button type="button" class="id-alerts-enable">Notify</button>
        ${withState ? '<span class="alerts-enable-state"></span>' : ""}
      </div>`;
    return document.querySelector(".alerts-enable");
  }

  function capable(reject) {
    window.PushManager = function () {};
    global.atob = (s) => Buffer.from(s, "base64").toString("binary");
    global.Notification = {
      requestPermission: jest.fn(() => Promise.resolve("granted")),
    };
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        register: jest.fn(() =>
          reject
            ? Promise.reject(reject)
            : Promise.resolve({
                pushManager: {
                  subscribe: jest.fn(() =>
                    Promise.resolve({ toJSON: () => ({}) })
                  ),
                },
              })
        ),
      },
    });
    global.fetch = jest.fn(() => Promise.resolve({ ok: true }));
  }

  afterEach(() => {
    delete window.PushManager;
    delete global.Notification;
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  test("a block with no state line still works", async () => {
    // Defensive: the template always renders the span. A throw here would lose
    // a subscription that had already been made.
    capable();
    const root = block({ withState: false });

    await expect(alerts.enablePush(root)).resolves.toBeDefined();
    expect(global.fetch).toHaveBeenCalled();
  });

  test("an error with no message still says something", async () => {
    // Some browsers reject with a DOMException whose message is empty, and
    // "nothing happened" is the one outcome a reader cannot act on.
    capable({});
    const root = block();

    await alerts.enablePush(root);

    expect(
      document.querySelector(".alerts-enable-state").textContent
    ).toMatch(/could not enable/i);
  });

  test("the CSRF cookie is sent when there is one", async () => {
    capable();
    document.cookie = "csrftoken=abc123";
    const root = block();

    await alerts.enablePush(root);

    expect(global.fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("abc123");
  });

  test("a stray enable button outside the block is ignored", () => {
    // `closest` finds nothing, and the handler must not call enablePush with
    // null - it reads dataset off it immediately.
    document.body.innerHTML = '<button class="id-alerts-enable">x</button>';

    expect(() => document.querySelector(".id-alerts-enable").click()).not.toThrow();
  });
});

describe("the period warm-up note", () => {
  /**
   * The note explains that a percentage rule reports nothing until it has a
   * total from a whole window ago. It is revealed and hidden with the period
   * selector because it lives *inside* that label - if a refactor moved it out,
   * it would sit under every subject explaining a control that is not there.
   */
  test("it is hidden with the period selector", () => {
    alerts.syncFields(panel("total_value"));

    expect(windowField().hidden).toBe(true);
    expect(windowField().querySelector(".alerts-window-note")).not.toBeNull();
  });

  test("it is revealed with the period selector", () => {
    alerts.syncFields(panel("total_percent"));

    expect(windowField().hidden).toBe(false);
    expect(windowField().querySelector(".alerts-window-note")).not.toBeNull();
  });
});

describe("where the toolbar ends up", () => {
  /**
   * `_swap_entry.html` lands near the top of the page, so the control renders
   * in a strip of its own above the heading - while Sweep dust, which does
   * exactly this, sits down in the row with Historic data and CSV export. Two
   * controls of the same kind in two different places.
   */
  test("it moves into the slot the sweep uses", () => {
    document.body.innerHTML =
      '<div id="top"><div id="id-alerts"></div></div>' +
      '<span id="id-dustsweep-slot"></span>';

    expect(alerts.placeToolbar()).toBe(true);
    expect(document.getElementById("id-alerts").parentNode.id).toBe(
      "id-dustsweep-slot"
    );
  });

  test("it is revealed once it is in place", () => {
    // **The jump a reader saw.** The partial lands near the top of the page and
    // the button belongs in the action row, so it is moved - and a move after
    // paint is a visible hop. It arrives `hidden` and this is what takes that
    // off, so the first sight of it is already in the right row.
    document.body.innerHTML =
      '<div id="top"><div id="id-alerts" hidden></div></div>' +
      '<span id="id-dustsweep-slot"></span>';

    alerts.placeToolbar();

    expect(document.getElementById("id-alerts").hidden).toBe(false);
  });

  test("a page with no slot still shows the button", () => {
    // Hidden-and-never-revealed is worse than the wrong row: the reader would
    // have no way to reach their alerts at all.
    document.body.innerHTML = '<div id="top"><div id="id-alerts" hidden></div></div>';

    expect(alerts.placeToolbar()).toBe(false);
    expect(document.getElementById("id-alerts").hidden).toBe(false);
  });

  test("a second call leaves it where it is", () => {
    // The partial arrives by swap and every swap calls this, so it runs many
    // times per page. Moving an element that is already in place would be a
    // needless reflow, and appending it again would reorder the row.
    document.body.innerHTML =
      '<span id="id-dustsweep-slot"><div id="id-alerts"></div></span>';

    expect(alerts.placeToolbar()).toBe(false);
  });

  test("no slot on the page leaves the toolbar alone", () => {
    // Not every page offering alerts offers the sweep's row.
    document.body.innerHTML = '<div id="top"><div id="id-alerts"></div></div>';

    expect(alerts.placeToolbar()).toBe(false);
    expect(document.getElementById("id-alerts").parentNode.id).toBe("top");
  });

  test("no toolbar is not an error", () => {
    document.body.innerHTML = '<span id="id-dustsweep-slot"></span>';

    expect(alerts.placeToolbar()).toBe(false);
  });
});

describe("picking an asset out of the search", () => {
  /** One result row, exactly as `swap/_assets.html` renders it. */
  function withResults() {
    const root = panel("asa_price");
    root.querySelector(".alerts-asset-results").innerHTML =
      '<ul class="swap-rows id-swap-asset-options">' +
      '<li class="swap-row id-swap-asset-option" data-id="31566704"' +
      ' data-unit="USDC" data-name="USDC"></li></ul>';
    return root;
  }

  test("the hidden field carries the id the form posts", () => {
    withResults();

    alerts.chooseAsset(document.querySelector(".id-swap-asset-option"));

    expect(document.querySelector(".alerts-asset-id").value).toBe("31566704");
  });

  test("the asset lands on the button and the picker closes", () => {
    // **The asset is the control now.** It used to be help text hanging off a
    // search box, which put the tool in front of the point.
    withResults();
    alerts.togglePicker(document.querySelector(".alerts-asset-field"), true);

    alerts.chooseAsset(document.querySelector(".id-swap-asset-option"));

    expect(
      document.querySelector(".alerts-assetbtn-text").textContent
    ).toContain("USDC");
    expect(document.querySelector(".alerts-picker").hidden).toBe(true);
  });

  test("typing without picking posts no asset", () => {
    // **Typing is not choosing.** An id guessed from a partial match would be
    // the wrong asset rather than no asset, and the form's own error is the
    // honest answer.
    const root = withResults();
    root.querySelector(".alerts-asset-search").value = "USDC";

    expect(document.querySelector(".alerts-asset-id").value).toBe("");
  });

  test("a row outside an asset field is ignored", () => {
    document.body.innerHTML =
      '<li class="swap-row id-swap-asset-option" data-id="1"></li>';

    expect(
      alerts.chooseAsset(document.querySelector(".id-swap-asset-option"))
    ).toBe(false);
  });
});

describe("the count on the button", () => {
  /** The toolbar as `_swap_entry.html` renders it, plus a swapped panel. */
  function mount(kept, left) {
    document.body.innerHTML =
      '<div id="id-alerts" data-rules-left="5">' +
      '<button class="alerts-open">Alerts' +
      '<span class="badge alerts-count" hidden>0</span></button></div>' +
      '<div class="alerts-panel" data-rules-kept="' + kept +
      '" data-rules-left="' + left + '"></div>';
    return document.querySelector(".alerts-panel");
  }

  const badge = () => document.querySelector(".alerts-count");
  const toolbar = () => document.getElementById("id-alerts");

  test("the first rule makes the badge appear", () => {
    // The bug as a reader met it: the modal said "4 of 5 left" over a button
    // that still showed none.
    const panel = mount(1, 4);

    expect(alerts.syncCount(panel)).toBe(true);
    expect(badge().textContent).toBe("1");
    expect(badge().hidden).toBe(false);
  });

  test("removing the last rule hides it again", () => {
    const panel = mount(0, 5);

    alerts.syncCount(panel);

    expect(badge().hidden).toBe(true);
  });

  test("the remaining allowance follows too", () => {
    const panel = mount(1, 4);

    alerts.syncCount(panel);

    expect(toolbar().getAttribute("data-rules-left")).toBe("4");
  });

  test("spending the allowance marks the button at its limit", () => {
    // `data-at-limit` is written by the template on first render; the modal is
    // the only place the number changes, so it is maintained here too.
    const panel = mount(5, 0);

    alerts.syncCount(panel);

    expect(
      document.querySelector(".alerts-open").getAttribute("data-at-limit")
    ).toBe("true");
  });

  test("freeing one clears the limit mark", () => {
    mount(5, 0);
    document.querySelector(".alerts-open").setAttribute("data-at-limit", "true");
    const panel = document.querySelector(".alerts-panel");
    panel.setAttribute("data-rules-kept", "4");
    panel.setAttribute("data-rules-left", "1");

    alerts.syncCount(panel);

    expect(
      document.querySelector(".alerts-open").hasAttribute("data-at-limit")
    ).toBe(false);
  });

  test("a panel without the counts changes nothing", () => {
    // The modal at its own URL renders a panel too; an older cached copy of it
    // would carry no attributes, and guessing zero would blank a real count.
    mount(2, 3);
    const panel = document.querySelector(".alerts-panel");
    panel.removeAttribute("data-rules-kept");

    expect(alerts.syncCount(panel)).toBe(false);
  });

  test("no toolbar on the page is not an error", () => {
    document.body.innerHTML =
      '<div class="alerts-panel" data-rules-kept="1" data-rules-left="4"></div>';

    expect(alerts.syncCount(document.querySelector(".alerts-panel"))).toBe(false);
  });
});

describe("the unit the threshold is typed in", () => {
  const hidden = () => document.querySelector(".alerts-unit-value");
  const usdButton = () => document.querySelector('[data-unit="usd"]');
  const note = () => document.querySelector(".alerts-now");

  test("the hidden field is what the form posts", () => {
    // The buttons are the visible state and `aria-pressed` is what a screen
    // reader is told; neither is what the server reads.
    panel("total_value");

    alerts.chooseUnit(usdButton());

    expect(hidden().value).toBe("usd");
  });

  test("only the pressed unit reads as pressed", () => {
    panel("total_value");

    alerts.chooseUnit(usdButton());

    expect(usdButton().getAttribute("aria-pressed")).toBe("true");
    expect(
      document.querySelector('[data-unit="algo"]').getAttribute("aria-pressed")
    ).toBe("false");
  });

  test("a percentage hides the unit control", () => {
    // A percentage is not a currency, so the control has nothing to say.
    const root = panel("total_percent");

    alerts.syncFields(root);

    expect(document.querySelector(".alerts-units").hidden).toBe(true);
  });

  test("a value subject shows it", () => {
    const root = panel("total_value");

    alerts.syncFields(root);

    expect(document.querySelector(".alerts-units").hidden).toBe(false);
  });
});

describe("the current value shown beside the threshold", () => {
  const note = () => document.querySelector(".alerts-now");

  test("the portfolio total is shown in ALGO", () => {
    const root = panel("total_value");

    expect(alerts.showCurrent(root)).toBe("Now 1000.00 ALGO");
  });

  test("choosing USD converts it at the rate the page carried", () => {
    // 1000 ALGO at $0.25.
    const root = panel("total_value");

    alerts.chooseUnit(document.querySelector('[data-unit="usd"]'));

    expect(note().textContent).toBe("Now $250.00");
  });

  test("a percentage has no current value to show", () => {
    const root = panel("total_percent");

    expect(alerts.showCurrent(root)).toBe("");
  });

  test("an asset subject shows nothing until an asset is picked", () => {
    // The price arrives on the search row; before one is chosen there is none,
    // and borrowing the portfolio total would be a different statement.
    const root = panel("asa_price");

    expect(alerts.showCurrent(root)).toBe("");
  });

  test("a holding subject shows nothing even with a price to hand", () => {
    // **`asa_total` is the value of this reader's holding**, which is not the
    // asset's price and is not published to this modal. The wrong number is
    // worse than none.
    const root = panel("asa_total");
    document.querySelector(".alerts-now").setAttribute("data-asset-usd", "0.25");

    expect(alerts.showCurrent(root)).toBe("");
  });

  test("a page that has never been re-priced shows nothing", () => {
    // Not zero, which would read as "your portfolio is worth nothing".
    const root = panel("total_value");
    note().setAttribute("data-current-total", "");

    expect(alerts.showCurrent(root)).toBe("");
  });
});

describe("the price of the asset a reader picked", () => {
  /** A picked asset priced at $0.25, with ALGO at $0.25. */
  function picked(assetUsd = "0.25", algoPerUsd = "4") {
    const root = panel("asa_price");
    const note = document.querySelector(".alerts-now");
    note.setAttribute("data-asset-usd", assetUsd);
    // **ALGO per USD**, the direction `priceusdc` actually holds - about 4 when
    // ALGO is $0.25. The old helper passed 0.25 and named it `algoUsd`, which
    // is how three conversions in this file came to run backwards while every
    // test passed: at that rate the right and wrong answers coincide.
    note.setAttribute("data-algo-per-usd", algoPerUsd);
    return root;
  }

  test("it is converted into ALGO, which is what the threshold means", () => {
    // **The two sides speak different currencies.** The search row carries USD;
    // the threshold is stored in ALGO. Showing the USD figure beside an ALGO
    // threshold without dividing would be the most dangerous version of this.
    const root = picked("0.50", "4");

    expect(alerts.showCurrent(root)).toBe("Now 2.00 ALGO");
  });

  test("choosing USD shows the price as it came", () => {
    const root = picked("0.50", "0.25");

    alerts.chooseUnit(document.querySelector('[data-unit="usd"]'));

    expect(document.querySelector(".alerts-now").textContent).toBe("Now $0.5");
  });

  test("a small price keeps its significant digits", () => {
    // A threshold of 0.0000123 is an ordinary ASA price; `toFixed(2)` would
    // render it 0.00 and tell the reader the asset is worthless.
    const root = picked("0.00000307", "4");

    expect(alerts.showCurrent(root)).toContain("0.00001228");
  });

  test("no ALGO price means no conversion and nothing shown", () => {
    const root = picked("0.50", "");

    expect(alerts.showCurrent(root)).toBe("");
  });

  test("the rate is ALGO per USD, not the other way round", () => {
    // **The direction, pinned with numbers that cannot both be right.** An
    // asset worth $2 where one dollar buys 4 ALGO is 8 ALGO, and the inverted
    // conversion this file shipped would say 0.50. Every earlier test used a
    // rate of 0.25, where dividing and multiplying by the reciprocal agree -
    // which is exactly why none of them caught it.
    const root = picked("2", "4");

    expect(alerts.showCurrent(root)).toBe("Now 8.00 ALGO");
  });
});


describe("the price of an asset the server chose", () => {
  /** A panel whose asset is already chosen, as editing renders it. */
  function bound(id) {
    const root = panel("asa_price");
    root.querySelector(".alerts-asset-id").value = id;
    root
      .querySelector(".alerts-asset-search")
      .setAttribute("hx-get", "/widgets/swap/assets");
    return root;
  }

  /** One result row, as `swap/_assets.html` renders it. */
  function results(id, price) {
    return (
      '<ul class="swap-rows id-swap-asset-options">' +
      '<li class="swap-row id-swap-asset-option" data-id="' + id + '"' +
      ' data-unit="USDC" data-usdc-price="' + price + '"></li></ul>'
    );
  }

  /** Let the fetch chain settle: a response, its `text()`, and two `then`s. */
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  afterEach(() => {
    delete global.fetch;
  });

  test("it is looked up when only the id is on the page", async () => {
    // **The gap a reader met on the two paths that matter most.** Editing a
    // rule, and a form that came back rejected, both render the asset already
    // chosen - and the price lived only in the search results, so those two
    // showed no reference at all.
    const root = bound("31566704");
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, text: () => Promise.resolve(results("31566704", "0.25")) })
    );

    expect(alerts.resolveAsset(root)).toBe(true);
    await flush();

    expect(global.fetch.mock.calls[0][0]).toBe("/widgets/swap/assets?q=31566704");
    expect(root.querySelector(".alerts-now").getAttribute("data-asset-usd")).toBe(
      "0.25"
    );
  });

  test("a price already on the page is not asked for again", () => {
    // It would be a request per swap for an answer the reader's own pick just
    // put there.
    const root = bound("31566704");
    root.querySelector(".alerts-now").setAttribute("data-asset-usd", "0.25");
    global.fetch = jest.fn();

    expect(alerts.resolveAsset(root)).toBe(false);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("no asset chosen asks nothing", () => {
    const root = bound("");
    global.fetch = jest.fn();

    expect(alerts.resolveAsset(root)).toBe(false);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test("only an exact id match is taken", async () => {
    // The endpoint ranks by name and unit as well as by id, so a query for one
    // asset can return several. Taking the first would hang another asset's
    // price off this rule - a reference figure that is confidently wrong.
    const root = bound("31566704");
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: true, text: () => Promise.resolve(results("999", "7.5")) })
    );

    alerts.resolveAsset(root);
    await flush();

    expect(root.querySelector(".alerts-now").getAttribute("data-asset-usd")).toBe(
      null
    );
  });

  test("a failed lookup says nothing", async () => {
    // A reference figure is an aid. A modal reporting its absence would be
    // worse than one that shows nothing.
    const root = bound("31566704");
    global.fetch = jest.fn(() => Promise.reject(new Error("offline")));

    expect(alerts.resolveAsset(root)).toBe(true);
    await flush();

    expect(root.querySelector(".alerts-now").textContent).toBe("");
  });

  test("a refused lookup says nothing either", async () => {
    const root = bound("31566704");
    global.fetch = jest.fn(() =>
      Promise.resolve({ ok: false, text: () => Promise.resolve("") })
    );

    alerts.resolveAsset(root);
    await flush();

    expect(root.querySelector(".alerts-now").getAttribute("data-asset-usd")).toBe(
      null
    );
  });
});


describe("the branches a reader reaches by clicking", () => {
  /** Click an element the way a reader does, through the delegated handler. */
  function click(element) {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }

  test("clicking a result row chooses that asset", () => {
    // The handler is delegated from the document and **scoped to this
    // widget's own results**: the swap window renders identical rows from the
    // same endpoint and has its own handler, so an unscoped selector would
    // make one picker answer for the other.
    const root = panel("asa_price");
    root.querySelector(".alerts-asset-results").innerHTML =
      '<ul class="swap-rows id-swap-asset-options">' +
      '<li class="swap-row id-swap-asset-option" data-id="31566704"' +
      ' data-unit="USDC" data-usdc-price="0.25"></li></ul>';

    click(document.querySelector(".id-swap-asset-option"));

    expect(document.querySelector(".alerts-asset-id").value).toBe("31566704");
  });

  test("clicking the asset button opens its picker", () => {
    const root = panel("asa_price");

    click(root.querySelector(".id-alerts-assetbtn"));

    expect(root.querySelector(".alerts-picker").hidden).toBe(false);
    expect(
      root.querySelector(".alerts-assetbtn").getAttribute("aria-expanded")
    ).toBe("true");
  });

  test("clicking it again closes it", () => {
    const root = panel("asa_price");
    const button = root.querySelector(".id-alerts-assetbtn");

    click(button);
    click(button);

    expect(root.querySelector(".alerts-picker").hidden).toBe(true);
  });
});

describe("what the swap handler ignores", () => {
  test("a swap of something else is not ours", () => {
    // Every htmx swap on the page reaches this, including ones from widgets
    // that know nothing about alerts. Acting on them would be the mirror of
    // the bug that made the modal never open.
    document.body.innerHTML = '<div id="elsewhere"><p>unrelated</p></div>';
    const swapped = document.getElementById("elsewhere");

    expect(
      alerts.handleSwap({ detail: { ctx: { target: swapped } }, target: swapped })
    ).toBe(false);
  });
});

describe("the current value with nothing to read it from", () => {
  test("a form with no subject shows nothing", () => {
    // A panel rendered without the subject select is not a state the server
    // produces, but this runs on every swap and on every unit change - it has
    // to survive markup it did not expect rather than throw inside a handler.
    const root = panel("asa_price");
    const note = root.querySelector(".alerts-now");
    note.textContent = "Now 4.00 ALGO";
    root.querySelector(".alerts-subject").remove();

    expect(alerts.showCurrent(root)).toBe("");
    expect(note.textContent).toBe("");
  });
});


describe("markup these handlers did not expect", () => {
  /**
   * **Why every one of these has a test.**
   *
   * Each is a guard or an `||` fallback, and all of them run against markup
   * the server renders - so the temptation is to call them unreachable and
   * move on. They are not: this widget's own panel is re-rendered by htmx
   * mid-edit, the toolbar is a *different* partial that may arrive later or
   * not at all, and both are read by handlers bound to the document. A guard
   * that has never once been executed is a guard nobody knows the behaviour
   * of, and the failures it prevents are silent ones - a picker that does not
   * open, a count that stops updating.
   */

  /** A panel with the asset field but nothing else the handlers look for. */
  function bare(html) {
    document.body.innerHTML = html;
    return document.querySelector(".alerts-panel") || document.body;
  }

  describe("handleSwap", () => {
    test("an event carrying nothing swappable is not ours", () => {
      expect(alerts.handleSwap({ detail: {}, target: null })).toBe(false);
    });

    test("a swapped node that cannot be queried is not ours", () => {
      // A text node reaches this the moment anything swaps one in.
      expect(
        alerts.handleSwap({ detail: {}, target: document.createTextNode("x") })
      ).toBe(false);
    });

    test("a detached panel is used when the document has none", () => {
      // `outerHTML` swaps leave `ctx.target` detached, so the live panel is
      // looked up in the document - and on the run where the swap *removed*
      // the panel there is nothing to find, leaving the detached one as the
      // only thing to sync against.
      const detached = document.createElement("div");
      detached.className = "alerts-panel";
      detached.setAttribute("data-rules-kept", "2");
      detached.setAttribute("data-rules-left", "3");
      document.body.innerHTML = "";

      expect(
        alerts.handleSwap({ detail: { ctx: { target: detached } }, target: detached })
      ).toBe(true);
    });
  });

  describe("chooseUnit", () => {
    test("a button outside a threshold field records nothing", () => {
      bare('<div class="alerts-panel"><button class="id-alerts-unit"></button></div>');

      expect(alerts.chooseUnit(document.querySelector(".id-alerts-unit"))).toBe(
        false
      );
    });

    test("a field with no hidden input records nothing", () => {
      bare(
        '<div class="alerts-panel"><label class="alerts-threshold-field">' +
          '<button class="id-alerts-unit" data-unit="usd"></button></label></div>'
      );

      expect(alerts.chooseUnit(document.querySelector(".id-alerts-unit"))).toBe(
        false
      );
    });

    test("a button with no unit means ALGO", () => {
      // The default the form itself falls back to, so the two cannot disagree.
      bare(
        '<div class="alerts-panel"><label class="alerts-threshold-field">' +
          '<button class="id-alerts-unit"></button>' +
          '<input class="alerts-unit-value" value="usd"></label></div>'
      );

      alerts.chooseUnit(document.querySelector(".id-alerts-unit"));

      expect(document.querySelector(".alerts-unit-value").value).toBe("algo");
    });

    test("a field outside any panel still updates", () => {
      // The reference line is looked up from the panel, and there is not
      // always one - the document is the fallback root.
      document.body.innerHTML =
        '<label class="alerts-threshold-field">' +
        '<button class="id-alerts-unit" data-unit="usd"></button>' +
        '<input class="alerts-unit-value" value="algo"></label>';

      expect(
        alerts.chooseUnit(document.querySelector(".id-alerts-unit"))
      ).toBe(true);
      expect(document.querySelector(".alerts-unit-value").value).toBe("usd");
    });
  });

  describe("showCurrent", () => {
    test("no unit control means the threshold is in ALGO", () => {
      const root = panel("total_value");
      root.querySelector(".alerts-unit-value").remove();

      expect(alerts.showCurrent(root)).toBe("Now 1000.00 ALGO");
    });
  });

  describe("syncCount", () => {
    /** The toolbar as `_swap_entry.html` renders it, parts optional. */
    function toolbar(inner) {
      const bar = document.createElement("div");
      bar.id = "id-alerts";
      bar.innerHTML = inner;
      document.body.appendChild(bar);
      return bar;
    }

    /** A panel carrying the two counts the toolbar copies. */
    function counted(kept, left) {
      const node = document.createElement("div");
      node.className = "alerts-panel";
      node.setAttribute("data-rules-kept", kept);
      node.setAttribute("data-rules-left", left);
      return node;
    }

    test("a toolbar with no badge still takes the allowance", () => {
      // The badge is absent for a reader who keeps none, in older markup and
      // in the upgrade variant - and the allowance still has to land.
      document.body.innerHTML = "";
      const bar = toolbar("<button class=\"alerts-open\"></button>");

      expect(alerts.syncCount(counted("1", "4"))).toBe(true);
      expect(bar.getAttribute("data-rules-left")).toBe("4");
    });

    test("a toolbar with no button still takes the allowance", () => {
      document.body.innerHTML = "";
      const bar = toolbar('<span class="alerts-count"></span>');

      expect(alerts.syncCount(counted("1", "4"))).toBe(true);
      expect(bar.querySelector(".alerts-count").textContent).toBe("1");
    });
  });

  describe("chooseAsset", () => {
    /** A field missing whichever part the test is about. */
    function field(inner) {
      document.body.innerHTML = '<div class="alerts-asset-field">' + inner + "</div>";
      return document.querySelector(".alerts-asset-field");
    }

    /** A result row with only the attributes named. */
    function row(attributes) {
      const node = document.createElement("li");
      node.className = "id-swap-asset-option";
      Object.keys(attributes).forEach((name) =>
        node.setAttribute(name, attributes[name])
      );
      return node;
    }

    test("a field with no hidden input records nothing", () => {
      const target = field('<button class="alerts-assetbtn"></button>');

      expect(alerts.chooseAsset(row({ "data-id": "1" }), target)).toBe(false);
    });

    test("a field with no unit input still records the asset", () => {
      // The unit is what the notification names the asset by, and it is
      // stored rather than looked up - but a panel rendered without the field
      // must still produce a working rule. The sentence falls back to the id.
      const target = field(
        '<input class="alerts-asset-id">' +
          '<button class="alerts-assetbtn"></button>'
      );

      expect(
        alerts.chooseAsset(row({ "data-id": "7", "data-unit": "USDC" }), target)
      ).toBe(true);
      expect(document.querySelector(".alerts-asset-id").value).toBe("7");
    });

    test("a field with no button records nothing", () => {
      const target = field('<input class="alerts-asset-id">');

      expect(alerts.chooseAsset(row({ "data-id": "1" }), target)).toBe(false);
    });

    test("a row with no id, no unit and no icon is still taken", () => {
      // **Every part of a result row is optional to this function.** The row
      // comes from another widget's template, so anything read out of it has
      // to survive that template changing - and the one thing that must not
      // happen is an exception inside a click handler.
      const target = field(
        '<input class="alerts-asset-id" value="7">' +
          '<input class="alerts-asset-unit" value="USDC">' +
          '<button class="alerts-assetbtn"></button>'
      );

      expect(alerts.chooseAsset(row({}), target)).toBe(true);
      expect(document.querySelector(".alerts-asset-id").value).toBe("");
      // The unit is cleared too rather than left describing the last asset -
      // a name that outlived its id is worse than no name.
      expect(document.querySelector(".alerts-asset-unit").value).toBe("");
    });

    test("a button with no label or icon is still usable", () => {
      const target = field(
        '<input class="alerts-asset-id">' +
          '<button class="alerts-assetbtn"></button>' +
          '<div class="alerts-picker"></div>'
      );

      expect(
        alerts.chooseAsset(
          row({ "data-id": "31566704", "data-unit": "USDC" }),
          target
        )
      ).toBe(true);
    });

    test("a field outside any panel and with no reference line", () => {
      // Both fallbacks at once: no `.alerts-panel` ancestor, so the document
      // is the root, and no `.alerts-now` in it to write the price onto.
      const target = field(
        '<input class="alerts-asset-id">' +
          '<button class="alerts-assetbtn">' +
          '<span class="alerts-assetbtn-text"></span>' +
          '<img class="alerts-assetbtn-icon"></button>'
      );

      expect(
        alerts.chooseAsset(
          row({ "data-id": "1", "data-usdc-price": "0.25" }),
          target
        )
      ).toBe(true);
    });
  });

  describe("resolveAsset", () => {
    test("a search box with no endpoint asks nothing", () => {
      const root = panel("asa_price");
      root.querySelector(".alerts-asset-id").value = "31566704";
      root.querySelector(".alerts-asset-search").removeAttribute("hx-get");

      expect(alerts.resolveAsset(root)).toBe(false);
    });
  });

  describe("togglePicker", () => {
    test("no field at all is not an error", () => {
      expect(alerts.togglePicker(null, true)).toBe(false);
    });

    test("a field with no picker is not an error", () => {
      document.body.innerHTML =
        '<div class="alerts-asset-field"><button class="alerts-assetbtn"></button></div>';

      expect(
        alerts.togglePicker(document.querySelector(".alerts-asset-field"), true)
      ).toBe(false);
    });

    test("a picker with no search box still opens", () => {
      // Opening focuses the search, and the focus is a convenience rather than
      // the feature - a picker that refused to open without one would be the
      // convenience breaking the thing it decorates.
      document.body.innerHTML =
        '<div class="alerts-asset-field">' +
        '<button class="alerts-assetbtn"></button>' +
        '<div class="alerts-picker" hidden></div></div>';

      expect(
        alerts.togglePicker(document.querySelector(".alerts-asset-field"), true)
      ).toBe(true);
      expect(document.querySelector(".alerts-picker").hidden).toBe(false);
    });
  });

  describe("the delegated click handler", () => {
    test("a click on something with no ancestors is ignored", () => {
      // `document` is the target when a click is dispatched on it directly,
      // and it has no `closest` - so the guard is what stops a TypeError
      // being thrown inside a handler bound to every click on the page.
      expect(() =>
        document.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      ).not.toThrow();
    });

    test("clicking a unit button records that unit", () => {
      const root = panel("total_value");
      const usd = root.querySelectorAll(".id-alerts-unit")[1];

      usd.dispatchEvent(new MouseEvent("click", { bubbles: true }));

      expect(root.querySelector(".alerts-unit-value").value).toBe("usd");
    });
  });
});

describe("offering a threshold to start from", () => {
  const input = () => document.querySelector(".alerts-threshold");
  const direction = () => document.querySelector(".alerts-direction");

  /** Choose a subject the way the panel's own change handler does. */
  function watch(subject) {
    const select = document.querySelector(".alerts-subject");
    select.value = subject;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  it("offers five percent above the total for a rule watching upwards", () => {
    // **A threshold equal to the current figure is the one value it must not
    // be.** A rule arms on its first reading and fires on a crossing, so
    // sitting it exactly on the figure triggers on the first wobble past it.
    panel();
    watch("total_value");

    expect(input().value).toBe("1050.00");
  });

  it("offers five percent below it for a rule watching downwards", () => {
    // Offering a threshold on the wrong side of the figure would be offering
    // a rule that fires the moment it is saved.
    panel();
    direction().value = "down";
    watch("total_value");

    expect(input().value).toBe("950.00");
  });

  it("re-offers on the other side when the direction changes", () => {
    panel();
    watch("total_value");
    expect(input().value).toBe("1050.00");

    direction().value = "down";
    direction().dispatchEvent(new Event("change", { bubbles: true }));

    expect(input().value).toBe("950.00");
  });

  it("falls back to the document for a direction outside a panel", () => {
    // The select is rendered inside the panel, so this is defensive - but a
    // delegated handler runs on whatever matches, and a `closest` miss here
    // would throw rather than do nothing.
    panel();
    const loose = document.createElement("select");
    loose.className = "alerts-direction";
    loose.innerHTML = '<option value="down" selected>Falls below</option>';
    document.body.appendChild(loose);
    watch("total_value");
    input().value = "";

    loose.dispatchEvent(new Event("change", { bubbles: true }));

    expect(input().value).toBe("1050.00");
  });

  it("never writes over what the reader typed", () => {
    // The whole feature has to be abandonable by typing one character, or it
    // is a field that argues with the person filling it in.
    panel();
    watch("total_value");
    input().value = "1234";

    direction().value = "down";
    direction().dispatchEvent(new Event("change", { bubbles: true }));

    expect(input().value).toBe("1234");
  });

  it("offers a price in the unit the reader is thinking in", () => {
    // The search row carries USD and the threshold is stored in ALGO, so the
    // offer has to follow the toggle exactly as the "Now" note does -
    // suggesting a dollar figure against an ALGO threshold is the most
    // dangerous version of this.
    panel();
    document.querySelector(".alerts-now").setAttribute("data-asset-usd", "0.25");
    watch("asa_price");

    expect(input().value).toBe("1.05");

    input().value = "";
    document
      .querySelector(".alerts-unit-value")
      .setAttribute("value", "usd");
    document.querySelector(".alerts-unit-value").value = "usd";
    window.asastatsAlerts.suggest(document);

    expect(input().value).toBe("0.2625");
  });

  it("offers nothing for a holding, because nothing here knows one", () => {
    // `asa_total` and `asa_amount` are about *this reader's holding*. The
    // panel is rendered for a page before an asset is chosen, and the picker
    // answers with the asset's price rather than with how much anybody holds.
    panel();
    document.querySelector(".alerts-now").setAttribute("data-asset-usd", "0.25");
    watch("asa_total");

    expect(input().value).toBe("");
    expect(window.asastatsAlerts.suggest(document)).toBe("");
  });

  it("offers nothing for a percentage, which is not a figure to nudge", () => {
    panel();
    watch("total_percent");

    expect(input().value).toBe("");
  });

  it("offers nothing when the panel has no threshold to fill", () => {
    panel();
    document.querySelector(".alerts-threshold").remove();

    expect(window.asastatsAlerts.suggest(document)).toBe("");
  });

  it("offers nothing when there is no form at all", () => {
    document.body.innerHTML = "";

    expect(window.asastatsAlerts.suggest(document)).toBe("");
  });

  it("reads no figure without a rate to convert one", () => {
    panel();
    document.querySelector(".alerts-now").removeAttribute("data-algo-per-usd");
    document.querySelector(".alerts-unit-value").value = "usd";
    watch("total_value");

    expect(window.asastatsAlerts.currentFigure(document)).toBe(null);
    expect(input().value).toBe("");
  });

  it("reads no figure from a panel with no note or no subject", () => {
    panel();
    document.querySelector(".alerts-now").remove();
    expect(window.asastatsAlerts.currentFigure(document)).toBe(null);

    panel();
    document.querySelector(".alerts-subject").remove();
    expect(window.asastatsAlerts.currentFigure(document)).toBe(null);
  });
});
