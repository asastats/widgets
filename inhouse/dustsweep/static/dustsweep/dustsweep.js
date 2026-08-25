/**
 * Dust Sweep controller.
 *
 * The loop is the whole design: ask the engine what to sign next, sign exactly
 * that, then ask again against whatever the chain now says. There is no plan
 * held on either side, so there is nothing to resume, nothing to invalidate and
 * no ordering to manage - "what is closeable now" is just current state.
 *
 * ## The part that matters: inspecting what we are asked to sign
 *
 * A close-out group is up to sixteen transactions that a user approves with one
 * click, and `asset_close_to` moves an entire balance. That is precisely the
 * shape the router contract's `_assert_group_is_clean` refuses to be bait for -
 * and the contract cannot help here, because these groups contain no
 * application call for it to refuse.
 *
 * So the group is decoded and checked **in the browser, against the plan that
 * described it**, before it reaches the wallet. Not because the engine is
 * expected to lie, but because "the engine said so" is the only other assurance
 * on offer, and a control that consists of trusting the thing it is meant to
 * check is not a control. Concretely this catches a response whose human-
 * readable description and actual bytes disagree - which is what a compromised
 * or confused engine, a cached answer or a mangled proxy would produce.
 *
 * There is no msgpack decoder on this page and pulling algosdk in for one is a
 * large dependency for a small job, so `decodeMsgpack` below reads the subset an
 * Algorand transaction actually uses. Addresses are compared as raw bytes,
 * which needs base32 only - encoding one back to text would need SHA-512/256,
 * which WebCrypto does not offer.
 */

/* ------------------------------------------------------------------ *
 * msgpack, enough of it to read a transaction
 * ------------------------------------------------------------------ */

/**
 * Decode the msgpack subset an Algorand transaction uses.
 *
 * Canonical transaction encoding omits every field at its zero value, uses
 * short string keys, and carries addresses as 32-byte binary. That is maps,
 * arrays, strings, binary and unsigned integers - no floats, no signed
 * integers, no extensions.
 *
 * @param {Uint8Array} bytes encoded transaction
 * @returns {Object} the decoded value
 */
function decodeMsgpack(bytes) {
  var at = 0;

  function u8() {
    return bytes[at++];
  }

  function uint(width) {
    var value = 0;
    for (var i = 0; i < width; i++) value = value * 256 + bytes[at++];
    return value;
  }

  function str(length) {
    var out = "";
    for (var i = 0; i < length; i++) out += String.fromCharCode(bytes[at++]);
    return out;
  }

  function bin(length) {
    var out = bytes.slice(at, at + length);
    at += length;
    return out;
  }

  function value() {
    var tag = u8();

    if (tag <= 0x7f) return tag; // positive fixint
    if (tag >= 0x80 && tag <= 0x8f) return map(tag - 0x80);
    if (tag >= 0x90 && tag <= 0x9f) return array(tag - 0x90);
    if (tag >= 0xa0 && tag <= 0xbf) return str(tag - 0xa0);

    switch (tag) {
      case 0xc0:
        return null;
      case 0xc2:
        return false;
      case 0xc3:
        return true;
      case 0xc4:
        return bin(uint(1));
      case 0xc5:
        return bin(uint(2));
      case 0xc6:
        return bin(uint(4));
      case 0xcc:
        return uint(1);
      case 0xcd:
        return uint(2);
      case 0xce:
        return uint(4);
      case 0xcf:
        return uint(8);
      case 0xd9:
        return str(uint(1));
      case 0xda:
        return str(uint(2));
      case 0xdc:
        return array(uint(2));
      case 0xde:
        return map(uint(2));
      default:
        throw new Error("unsupported msgpack tag 0x" + tag.toString(16));
    }
  }

  function map(size) {
    var out = {};
    for (var i = 0; i < size; i++) {
      var key = value();
      out[key] = value();
    }
    return out;
  }

  function array(size) {
    var out = [];
    for (var i = 0; i < size; i++) out.push(value());
    return out;
  }

  return value();
}

/** Decode a base64 string to a Uint8Array (browser, no Buffer). */
function b64ToBytes(b64) {
  var bin = atob(b64);
  var out = new Uint8Array(bin.length);
  for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

var BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/**
 * Return the 32 public-key bytes of an Algorand address.
 *
 * The text form is base32 of the key plus a four-byte checksum; the checksum is
 * dropped rather than verified, because verifying it needs SHA-512/256 and
 * WebCrypto has no such digest. Nothing here depends on it: these addresses come
 * from our own plan, and what is being tested is whether the *transaction*
 * matches them.
 *
 * @param {string} address Algorand address in its text form
 * @returns {Uint8Array|null} 32 bytes, or null when the address is unreadable
 */
function addressToBytes(address) {
  if (typeof address !== "string" || address.length !== 58) return null;

  var out = new Uint8Array(32);
  var buffer = 0;
  var bits = 0;
  var written = 0;
  for (var i = 0; i < address.length; i++) {
    var digit = BASE32.indexOf(address[i]);
    if (digit < 0) return null;

    buffer = (buffer << 5) | digit;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      if (written < 32) out[written++] = (buffer >> bits) & 0xff;
    }
  }
  // 58 base32 characters carry 290 bits, so the loop above always fills all
  // 32 bytes before the guard stops it - there is no short-read case left to
  // check once the length and the alphabet have been.
  return out;
}

/** Return whether two byte arrays hold the same bytes. */
function sameBytes(left, right) {
  if (!left || !right || left.length !== right.length) return false;

  for (var i = 0; i < left.length; i++) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

/* ------------------------------------------------------------------ *
 * the whitelist
 * ------------------------------------------------------------------ */

/** How many close-outs one group may carry; `MaxTxGroupSize` is sixteen. */
var CLOSE_OUTS_PER_GROUP = 16;

/**
 * Return every reason this group is not the close-out group it was described as.
 *
 * Structural, not advisory: each rule refuses a transaction shape rather than
 * judging an amount, so passing all of them means the group can do nothing
 * except empty the holdings the plan listed into the targets the plan named.
 *
 * The rules, and what each one is stopping:
 *
 * - **`axfer` only, never `pay`.** A payment's `close` field drains the entire
 *   ALGO balance to whoever it names. It has no legitimate place in a sweep, and
 *   it is the single most damaging thing that could hide in a batch of sixteen.
 * - **zero amount.** `asset_close_to` moves the whole balance by itself, so a
 *   sweep never needs to name an amount - and one that did could send tokens
 *   somewhere the close-out then does not.
 * - **sender and receiver are both the holder.** The transfer half is a no-op
 *   and only the close is doing anything.
 * - **no rekey.** A rekey hands the account away permanently. It is the reason
 *   `_assert_group_is_clean` exists.
 * - **the close target is the one the plan named for that asset**, matched by
 *   asset id - self for an empty holding, the asset's creator for a forfeit.
 *   This is what makes the check bind rather than merely restate the response:
 *   a group that closes a *different* asset, or the right asset to a different
 *   address, fails here even though it is a perfectly well-formed close-out.
 *
 * @param {Array<string>} encoded base64 msgpack transactions, in group order
 * @param {string} address the account being swept
 * @param {Array<Object>} described the plan's holdings for this group
 * @returns {Array<string>} problems, empty when the group is what it claimed
 */
function closeOutProblems(encoded, address, described) {
  var problems = [];
  var owner = addressToBytes(address);
  if (!owner) return ["the address being swept is unreadable"];

  if (!Array.isArray(encoded) || encoded.length === 0) {
    return ["the group carries no transactions"];
  }

  if (encoded.length > CLOSE_OUTS_PER_GROUP) {
    problems.push(
      "the group carries " + encoded.length + " transactions, over the limit of " +
        CLOSE_OUTS_PER_GROUP
    );
  }

  var expected = {};
  (described || []).forEach(function (one) {
    // an empty holding closes to itself; a forfeit closes to the creator
    expected[one.asset] = Number(one.amount) === 0 ? address : one.creator;
  });

  encoded.forEach(function (raw, index) {
    var where = "transaction " + (index + 1) + " ";
    var txn;
    try {
      txn = decodeMsgpack(b64ToBytes(raw));
    } catch (error) {
      problems.push(where + "could not be decoded");
      return;
    }

    if (txn.type !== "axfer") {
      problems.push(where + "is a " + txn.type + ", not an asset transfer");
      return;
    }

    if (txn.aamt) problems.push(where + "moves an amount rather than closing");
    if (txn.rekey) problems.push(where + "rekeys the account");
    if (!sameBytes(txn.snd, owner)) problems.push(where + "is not sent by you");
    if (!sameBytes(txn.arcv, owner)) problems.push(where + "pays somebody else");

    if (!txn.aclose) {
      problems.push(where + "does not close the holding");
      return;
    }

    var target = expected[txn.xaid];
    if (target === undefined) {
      problems.push(where + "closes asset " + txn.xaid + ", which was not listed");
      return;
    }

    if (!sameBytes(txn.aclose, addressToBytes(target))) {
      problems.push(where + "closes asset " + txn.xaid + " to an unexpected address");
    }
  });

  return problems;
}

/* ------------------------------------------------------------------ *
 * the loop
 * ------------------------------------------------------------------ */

/**
 * Ask the engine what to sign next for `address`.
 *
 * @param {string} planUrl the widget's plan endpoint
 * @param {string} address the account being swept
 * @param {Object} options threshold and opt-in choices
 * @returns {Promise<Object>} the plan
 */
async function fetchPlan(planUrl, address, options) {
  var response = await fetch(planUrl + "?address=" + encodeURIComponent(address), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(options || {}),
  });
  var body = await response.json();
  if (!response.ok) {
    throw new Error((body && body.error) || "the sweep is unavailable");
  }
  return body;
}

/** Return the CSRF token Django set, or "" when there is none. */
function csrfToken() {
  var match = document.cookie.match(/(^|;\s*)csrftoken=([^;]*)/);
  return match ? decodeURIComponent(match[2]) : "";
}

/**
 * Sign and submit the action the plan chose, refusing anything unexpected.
 *
 * A conversion goes through `signAndSendPartial`, which preserves the engine's
 * quote-authorisation signature; a close-out group is all-user-signed and goes
 * through `signAndSend`. Only the close-out path is inspected here - a
 * conversion carries a router call the contract itself checks, including its
 * refusal of any group containing a close.
 *
 * @param {Object} action the plan's `next`
 * @param {string} address the account being swept
 * @param {Object} bridge window.asastatsSwap
 * @returns {Promise<string>} the submitted transaction id
 */
async function signAction(action, address, bridge) {
  if (action.kind === "convert") {
    if (typeof bridge.signAndSendPartial !== "function") {
      throw new Error("The connected wallet does not support quote-signed groups");
    }
    return await bridge.signAndSendPartial(action);
  }

  var problems = closeOutProblems(action.transactions, address, action.holdings);
  if (problems.length) {
    throw new Error("This group was refused: " + problems.join("; "));
  }

  return await bridge.signAndSend(action.transactions, {});
}

/**
 * Run `fn` once the swap bridge is available.
 *
 * The bridge publishes `window.asastatsSwap` and dispatches
 * `asastats:swap-ready` only after the wallet manager resumes, so anything
 * reading `activeAddress` has to wait for it.
 */
function whenSweepReady(fn) {
  if (window.asastatsSwap) {
    fn();
  } else {
    window.addEventListener("asastats:swap-ready", fn, { once: true });
  }
}

/**
 * Return the sentence describing what a plan will do, for the panel heading.
 *
 * @param {Object} plan the engine's answer
 * @returns {string} a sentence
 */
function summarise(plan) {
  var summary = plan.summary || {};
  if (!plan.next) {
    return summary.unpriced
      ? "Nothing to sweep. " + summary.unpriced +
          " holdings could not be valued and were left alone."
      : "Nothing to sweep.";
  }

  var recoverable = ((summary.recoverable || 0) / 1e6).toFixed(1);
  return (
    summary.prompts +
    (summary.prompts === 1 ? " signature" : " signatures") +
    " to recover about " +
    recoverable +
    " ALGO"
  );
}

/* istanbul ignore next -- DOM wiring; the unit-tested core is the helpers above */
function start() {
  var root = document.getElementById("id-dustsweep");
  if (!root) return;

  var planUrl = root.dataset.planUrl;
  root.querySelectorAll(".id-dustsweep-panel").forEach(function (panel) {
    var details = panel.closest("details");
    if (!details) return;

    details.addEventListener("toggle", function () {
      if (details.open && !panel.dataset.loaded) {
        panel.dataset.loaded = "1";
        refresh(panel, planUrl, panel.dataset.address);
      }
    });
  });
}

/* istanbul ignore next -- DOM wiring */
async function refresh(panel, planUrl, address) {
  panel.textContent = "Reading your holdings…";
  try {
    var plan = await fetchPlan(planUrl, address, {});
    render(panel, planUrl, address, plan);
  } catch (error) {
    panel.textContent = "Could not plan a sweep: " + error.message;
  }
}

/* istanbul ignore next -- DOM wiring */
function render(panel, planUrl, address, plan) {
  panel.textContent = "";
  var heading = document.createElement("p");
  heading.textContent = summarise(plan);
  panel.appendChild(heading);

  if (!plan.next) return;

  var why = document.createElement("p");
  why.className = "dustsweep-why";
  why.textContent = plan.next.label + " — " + plan.next.why;
  panel.appendChild(why);

  var button = document.createElement("button");
  button.type = "button";
  button.className = "dustsweep-sign";
  button.textContent = plan.next.label;
  button.addEventListener("click", async function () {
    button.disabled = true;
    try {
      await signAction(plan.next, address, window.asastatsSwap);
      refresh(panel, planUrl, address);
    } catch (error) {
      why.textContent = error.message;
      button.disabled = false;
    }
  });
  panel.appendChild(button);
}

/* istanbul ignore else -- in the browser we self-start; under jest we export */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    CLOSE_OUTS_PER_GROUP: CLOSE_OUTS_PER_GROUP,
    addressToBytes: addressToBytes,
    b64ToBytes: b64ToBytes,
    closeOutProblems: closeOutProblems,
    csrfToken: csrfToken,
    decodeMsgpack: decodeMsgpack,
    fetchPlan: fetchPlan,
    sameBytes: sameBytes,
    signAction: signAction,
    summarise: summarise,
    whenSweepReady: whenSweepReady,
  };
} else {
  whenSweepReady(start);
}
