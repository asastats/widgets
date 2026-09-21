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
    <div class="alerts-panel">
      <form class="alerts-form">
        <select class="alerts-subject">
          <option value="asa_price">Asset price</option>
          <option value="asa_total">My holding of an asset</option>
          <option value="total_value">Portfolio total</option>
          <option value="total_percent">Portfolio total, percentage move</option>
        </select>
        <label class="alerts-field alerts-asset-field" hidden>
          <input type="number" name="asset_id">
        </label>
        <label class="alerts-field alerts-window-field" hidden>
          <select name="window_seconds"><option value="3600">1 hour</option></select>
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
