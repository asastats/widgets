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

/** What one holding's opt-in locks, and so what closing it returns. */
var HOLDING_MINIMUM_BALANCE = 100000;

/**
 * The most a single close-out may pay the network, in microALGO.
 *
 * **Expressed as a fraction of what a close-out returns, deliberately.** The
 * number happens to be ten times the protocol minimum of 1,000, which is the
 * headroom a congested network needs - the engine builds these from the node's
 * suggested parameters, and a bound pinned at the minimum would refuse honest
 * groups. But the property worth keeping is the other one: at the limit, a
 * close-out still returns nine tenths of the minimum balance it releases.
 *
 * Writing it this way makes a whole-group rule unnecessary rather than merely
 * redundant. A group of `n` close-outs releases `n * HOLDING_MINIMUM_BALANCE`
 * and can pay at most a tenth of that, so "the fees exceed what the group
 * recovers" is unreachable by construction and there is nothing to check for
 * it. Raise this above `HOLDING_MINIMUM_BALANCE` and that stops being true.
 */
var MAX_CLOSE_OUT_FEE = HOLDING_MINIMUM_BALANCE / 10;

/**
 * Return the plan lines that are shaped like plan lines, and nothing else.
 *
 * **Both checks below take `described` from an HTTP response, so its shape is
 * not theirs to assume.** They used to reach straight for
 * `(described || []).forEach`, which is fine for an array and throws for
 * everything else -- a string, a number, a bare object. `closeOutProblems`
 * already guarded the *group* with `Array.isArray` and did not guard the
 * description, and that asymmetry was the whole of it.
 *
 * Found by the property tests in `dustsweep.property.test.js` on their first
 * run. The example suite covers `undefined` and `[]`, which are the two ways
 * an *array* can be missing, and no way for the field to be something else.
 *
 * An unreadable description yields no expected targets, so every transaction
 * then fails the "was not listed" rule and the group is refused. Degrading to
 * a refusal is the safe direction and the one the rest of this file takes.
 *
 * @param {*} described whatever arrived as the plan's holdings
 * @returns {Array<Object>} the lines that can be read
 */
function planLines(described) {
  if (!Array.isArray(described)) return [];

  return described.filter(function (one) {
    return one && typeof one === "object";
  });
}

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
 *   A group that closes a *different* asset, or the right asset to a different
 *   address, fails here even though it is a perfectly well-formed close-out.
 * - **the fee is bounded**, per transaction and across the group. Nothing else
 *   bounds it: the engine sets it from the node's suggested parameters and the
 *   bridge preserves whatever arrives. Mainnet will take a fee up to the
 *   account's entire spendable balance, so a sweep that emptied an account
 *   without moving a single token was a valid group. See `MAX_CLOSE_OUT_FEE`.
 *
 * **What this function cannot do, and `forfeitTargetProblems` does.** For an
 * *empty* holding the expected close target is the connected account, which is
 * known independently of the response. For a *forfeit* it is
 * `described[].creator`, which arrives in the same payload as the bytes - so a
 * response that is internally consistent passes, whatever address it names.
 * That was the audit's `S2`. The rule below still earns its place, because it
 * catches bytes that disagree with what the reader was shown; but the forfeit
 * destination is confirmed against the chain, separately and asynchronously.
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
  planLines(described).forEach(function (one) {
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

    // A decode that *succeeds* and yields something that is not a transaction
    // is the case the catch above cannot see. "wA" is valid base64 for the
    // single msgpack byte 0xc0 -- nil -- so `decodeMsgpack` returns null and
    // every field read below throws instead of being reported. Anything that
    // is not an object gets the same answer as a failed decode, because from
    // here they are the same thing: no transaction to check.
    if (!txn || typeof txn !== "object") {
      problems.push(where + "could not be decoded");
      return;
    }

    if (txn.type !== "axfer") {
      problems.push(where + "is a " + txn.type + ", not an asset transfer");
      return;
    }

    if ((Number(txn.fee) || 0) > MAX_CLOSE_OUT_FEE) {
      problems.push(
        where + "pays a fee of " + algo(txn.fee) + " ALGO, over the limit of " +
          algo(MAX_CLOSE_OUT_FEE)
      );
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

/**
 * Return every forfeit destination the chain does not agree with.
 *
 * **This is the half of the check that does not come from the response.**
 * `closeOutProblems` compares a forfeit's `asset_close_to` against
 * `described[].creator`, and both halves of that comparison arrive in the same
 * JSON: an engine that names an address it controls in `holdings` and closes
 * to it in `transactions` is internally consistent, so the check passes. That
 * was the audit's `S2`, and it defeated the stated purpose of the whitelist -
 * a control that consists of trusting the thing it is meant to check.
 *
 * So the creator is resolved from the chain instead, through the wallet
 * bridge's own algod connection, and the transaction is compared against
 * *that*. One lookup per distinct asset, memoised, and only for holdings the
 * plan says still carry a balance - an empty holding closes to the connected
 * account, which was never in doubt.
 *
 * **It fails closed.** A bridge too old to expose `assetCreator`, an
 * unreachable node, or an asset whose parameters cannot be read all produce a
 * problem rather than a pass. Refusing to sign costs a reader one sweep;
 * signing an unverifiable forfeit costs them the holding. Empty holdings are
 * unaffected either way, and they are where most of what a sweep recovers is.
 *
 * @param {Array<string>} encoded base64 msgpack transactions, in group order
 * @param {Array<Object>} described the plan's holdings for this group
 * @param {Object} bridge window.asastatsSwap
 * @returns {Promise<Array<string>>} problems, empty when every forfeit agrees
 */
async function forfeitTargetProblems(encoded, described, bridge) {
  var forfeited = {};
  planLines(described).forEach(function (one) {
    if (Number(one.amount) !== 0) forfeited[one.asset] = true;
  });
  if (!Object.keys(forfeited).length) return [];

  if (!bridge || typeof bridge.assetCreator !== "function") {
    return [
      "this wallet connection cannot confirm who an asset's creator is, and " +
        "the sweep will not give a holding away on the engine's word alone",
    ];
  }

  var problems = [];
  var resolved = {};
  for (var index = 0; index < encoded.length; index++) {
    var txn;
    try {
      txn = decodeMsgpack(b64ToBytes(encoded[index]));
    } catch (error) {
      continue; // closeOutProblems has already refused this group
    }

    if (!forfeited[txn.xaid]) continue;

    if (!(txn.xaid in resolved)) {
      try {
        resolved[txn.xaid] = await bridge.assetCreator(txn.xaid);
      } catch (error) {
        resolved[txn.xaid] = null;
      }
    }

    var where = "transaction " + (index + 1) + " ";
    if (!resolved[txn.xaid]) {
      problems.push(
        where + "forfeits asset " + txn.xaid + ", whose creator could not be " +
          "confirmed on chain"
      );
    } else if (!sameBytes(txn.aclose, addressToBytes(resolved[txn.xaid]))) {
      problems.push(
        where + "forfeits asset " + txn.xaid + " to an address that is not " +
          "its creator on chain"
      );
    }
  }

  return problems;
}

/* ------------------------------------------------------------------ *
 * what each disposition means to a reader
 * ------------------------------------------------------------------ */

/**
 * How each disposition is labelled, and whether it is swept by default.
 *
 * **`included` is the whole of the per-line policy**, and the asymmetry in it
 * is deliberate. Everything the engine could value is swept unless the reader
 * says otherwise; `unpriced` is the one disposition that starts *off*, because
 * it is the one where the engine is admitting it does not know what the token
 * is worth. Turning it on is the reader accepting that, line by line, which is
 * the only way an unvalued holding is ever given away.
 *
 * `keep` has no entry: it is not actionable, so it carries no control at all
 * rather than a disabled one.
 */
var DISPOSITIONS = {
  close: { label: "Close", included: true, tone: "close" },
  forfeit: { label: "Forfeit", included: true, tone: "forfeit" },
  convert: { label: "Convert", included: true, tone: "convert" },
  unpriced: { label: "Unpriced", included: false, tone: "unpriced" },
};

/**
 * Dispositions the reader can see but cannot act on, and their badges.
 *
 * **Deliberately a second map rather than `included: false` entries.** Anything
 * in `DISPOSITIONS` is *actionable*: the row grows a checkbox, and switching it
 * on puts the asset in `opted_in`. That is right for `unpriced`, which is a
 * holding the sweep could take if the reader vouches for it, and wrong for
 * these two, which the engine will refuse whatever the body says. A checkbox
 * that quietly does nothing is worse than no checkbox.
 */
var INERT = {
  keep: { label: "Keep", tone: "keep" },
  committed: { label: "In use", tone: "committed" },
};

/** Return whether a sweep can do anything at all with this holding. */
function isActionable(holding) {
  return Object.prototype.hasOwnProperty.call(DISPOSITIONS, holding.disposition);
}

/** Return the badge a holding wears, actionable or not. */
function badgeFor(holding) {
  return (
    DISPOSITIONS[holding.disposition] || INERT[holding.disposition] || INERT.keep
  );
}

/**
 * Return the two texts that name a holding's asset: its unit, and its id.
 *
 * **The id is shown, not just carried.** A unit name is not an identity -
 * anyone can mint a second "USDC" - and the asset id is the only handle a
 * reader can paste into an explorer to see what they are about to close out or
 * give away. It is also the fallback name: `_asset_facts` returns no unit for
 * an asset whose parameters could not be read, and a row labelled with nothing
 * is a row nobody can check.
 *
 * @param {Object} holding a plan line
 * @returns {{unit: string, id: string}}
 */
function assetLabels(holding) {
  return {
    unit: (holding && holding.unit) || "Unnamed",
    id: "#" + ((holding && holding.asset) != null ? holding.asset : "?"),
  };
}

/** Return whether this holding is swept unless the reader says otherwise. */
function includedByDefault(holding) {
  var meta = DISPOSITIONS[holding.disposition];
  return meta ? meta.included : false;
}

/**
 * Return whether this holding is currently going to be swept.
 *
 * @param {Object} holding a plan line
 * @param {Map} choices asset id to the reader's explicit choice
 * @returns {boolean}
 */
function isIncluded(holding, choices) {
  if (choices && choices.has(holding.asset)) return choices.get(holding.asset);

  return includedByDefault(holding);
}

/**
 * Return the two per-line lists the engine takes, from the reader's choices.
 *
 * Only *deviations* from the default are sent, which is what lets the plan be
 * refetched after every signature without the reader's decisions being reset:
 * a holding that appears for the first time takes its default, and one they
 * touched keeps what they said.
 *
 * The two lists are not mirror images. `opted_in` widens what the sweep gives
 * away and `excluded` narrows it, so a holding can only reach `opted_in` by
 * being unvalued and switched on, and can only reach `excluded` by being
 * something the engine would otherwise have swept.
 *
 * @param {Array<Object>} holdings the plan's holdings
 * @param {Map} choices asset id to the reader's explicit choice
 * @returns {{opted_in: Array<number>, excluded: Array<number>}}
 */
function choicePayload(holdings, choices) {
  var optedIn = [];
  var excluded = [];
  (holdings || []).forEach(function (holding) {
    if (!isActionable(holding)) return;

    var wanted = isIncluded(holding, choices);
    if (includedByDefault(holding)) {
      if (!wanted) excluded.push(holding.asset);
    } else if (wanted) {
      optedIn.push(holding.asset);
    }
  });
  return { opted_in: optedIn, excluded: excluded };
}

/**
 * Return the holdings a filter should show.
 *
 * "sweeping" is the default view because a reader opening a sweep wants to see
 * what is about to happen, not an inventory. "all" exists so the holdings the
 * sweep decided to leave alone are still visible - a reader who cannot see why
 * their token was skipped has no way to tell "kept deliberately" from "missed".
 *
 * @param {Array<Object>} holdings the plan's holdings
 * @param {string} filter "sweeping" or "all"
 * @returns {Array<Object>}
 */
function visibleLines(holdings, filter) {
  if (filter === "all") return (holdings || []).slice();

  return (holdings || []).filter(isActionable);
}

/* ------------------------------------------------------------------ *
 * the loop
 * ------------------------------------------------------------------ */

/**
 * Ask the engine what to sign next for `address`.
 *
 * @param {string} planUrl the widget's plan endpoint
 * @param {string} address the account being swept
 * @param {Object} options threshold and the two per-line lists
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
 * Return the engine's conversion payload in the shape the bridge signs.
 *
 * The wire format and the bridge's format are not the same thing, and it is
 * `swap.js`'s `AsastatsAdapter.buildSwapGroup` that says what the difference
 * is: JSON carries base64 and snake_case, `signAndSendPartial` wants decoded
 * bytes and camelCase. Written out here rather than borrowed, because the two
 * widgets ship separately and neither may import the other's module.
 *
 * @param {Object} action the plan's `next`, kind "convert"
 * @returns {Object} `{transactions, signedTransactions, quoteSignerIndex}`
 */
function partialGroup(action) {
  var signed = {};
  Object.keys(action.signed_transactions || {}).forEach(function (index) {
    signed[index] = b64ToBytes(action.signed_transactions[index]);
  });
  return {
    transactions: (action.transactions || []).map(b64ToBytes),
    signedTransactions: signed,
    quoteSignerIndex: Number(action.quote_signer_index),
  };
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
 * **Both bridge methods take decoded bytes, and this used to hand them the
 * base64.** `signAndSend(group: Uint8Array[])` passes each entry straight to
 * `decodeUnsignedTransaction`, which coerces a string array-like into one byte
 * per *character* - so a 340-character close-out arrived as 340 zero bytes and
 * msgpack read one complete object in the first of them:
 *
 *     RangeError: Extra 339 of 340 byte(s) found at buffer[1]
 *
 * which named neither base64 nor this widget. The conversion path had the same
 * fault in a second form, passing the whole JSON action where the bridge wants
 * three named fields, and would have failed its own way at the first signature.
 * Decoding is therefore done here, at the single point where the wire format
 * becomes an argument.
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
    return await bridge.signAndSendPartial(partialGroup(action));
  }

  var problems = closeOutProblems(action.transactions, address, action.holdings);
  if (!problems.length) {
    // Only once the group is structurally what it claimed, because this half
    // costs a network round trip per forfeited asset and there is nothing to
    // confirm about a group that has already been refused.
    problems = await forfeitTargetProblems(
      action.transactions,
      action.holdings,
      bridge
    );
  }
  if (problems.length) {
    throw new Error("This group was refused: " + problems.join("; "));
  }

  // No `|| []` guard: `closeOutProblems` has already refused anything that is
  // not a non-empty array, and threw above.
  return await bridge.signAndSend(action.transactions.map(b64ToBytes), {});
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
 * Return the account the sweep entry may offer, or "".
 *
 * **A sweep is only ever offered for the account the wallet is connected to.**
 * Every other address is unofferable by construction: the group is signed by one
 * key, the wallet holds one active account, and a button for any other account
 * builds transactions that account cannot sign. The reader used to discover that
 * at the signature prompt.
 *
 * Both halves of the question are asked here. `candidates` is what the server
 * knows - the reader's own addresses among those this page shows - and `active`
 * is what the browser knows. An account that is connected but not on this page
 * is not offered either: the sweep acts on what the reader is looking at.
 *
 * @param {string[]} candidates addresses this page shows and the reader owns
 * @param {string} active the wallet's connected account, or "" / null
 * @returns {string} the address to sweep, or "" when there is none
 */
function sweepableAddress(candidates, active) {
  if (!active || !candidates) return "";
  for (var i = 0; i < candidates.length; i++) {
    if (candidates[i] === active) return active;
  }
  return "";
}

/**
 * Return an address shortened for a button label.
 *
 * @param {string} address a full Algorand address
 * @returns {string} e.g. "STATS6…4PK2Q", or "" for nothing
 */
function shortAddress(address) {
  if (!address) return "";
  return address.slice(0, 6) + "…" + address.slice(-4);
}

/* ------------------------------------------------------------------ *
 * what the reader is told
 * ------------------------------------------------------------------ */

/** Return microALGO as a short ALGO string. */
function algo(microalgo) {
  return ((Number(microalgo) || 0) / 1e6).toFixed(2);
}

/**
 * Return the three figures the summary strip shows.
 *
 * `recoverable` is the minimum balance alone, net of fees - the certain half.
 * A close returns exactly 0.1 ALGO whatever the token is worth, while
 * conversion proceeds depend on quotes not taken yet, and promising the
 * uncertain half up front is how a sweep ends up having under-delivered.
 *
 * **Fees are shown, not folded away.** `summary.fees` was computed by the
 * planner and sent here from the beginning, and nothing rendered it: there was
 * no number on this screen that would have moved if every fee in the group had
 * been a thousand times larger, which is the reporting half of the audit's
 * `S3`. It sits beside what the sweep returns because the two are the same
 * arithmetic, and a reader comparing them can see a sweep that is not worth
 * signing.
 *
 * @param {Object} plan the engine's answer
 * @returns {Array<{label: string, value: string}>}
 */
function summaryFigures(plan) {
  var summary = (plan && plan.summary) || {};
  var swept =
    (summary.close || 0) + (summary.forfeit || 0) + (summary.convert || 0);
  return [
    { label: "You recover", value: algo(summary.recoverable) + " ALGO" },
    { label: "Network fees", value: algo(summary.fees) + " ALGO" },
    { label: "Signatures", value: String(summary.prompts || 0) },
    { label: "Holdings", value: String(swept) },
  ];
}

/**
 * Return the sentence describing what a plan will do.
 *
 * @param {Object} plan the engine's answer
 * @returns {string} a sentence
 */
function summarise(plan) {
  var summary = (plan && plan.summary) || {};
  if (!plan || !plan.next) {
    return summary.unpriced
      ? "Nothing to sweep. " + summary.unpriced +
          " holdings could not be valued and were left alone."
      : "Nothing to sweep.";
  }

  return (
    summary.prompts +
    (summary.prompts === 1 ? " signature" : " signatures") +
    " to recover about " +
    algo(summary.recoverable) +
    " ALGO"
  );
}

/**
 * Return the label the primary action should carry.
 *
 * @param {Object} plan the engine's answer
 * @returns {string}
 */
function ctaLabel(plan) {
  if (!plan || !plan.next) return "Nothing to sweep";

  return plan.next.label
    ? plan.next.label.charAt(0).toUpperCase() + plan.next.label.slice(1)
    : "Sign the next group";
}

/**
 * Return the progress line, or "" when there is nothing in flight.
 *
 * Counts signatures rather than percentages, because that is the unit the
 * reader is actually spending and the only one they can plan around.
 *
 * @param {Object} plan the engine's answer
 * @param {number} signed how many groups have been signed in this session
 * @returns {string}
 */
function progressLabel(plan, signed) {
  var remaining = ((plan && plan.summary) || {}).prompts || 0;
  if (!remaining && !signed) return "";

  return "Signature " + (signed + 1) + " of " + (signed + remaining);
}

/* ------------------------------------------------------------------ *
 * DOM
 * ------------------------------------------------------------------ */

/* istanbul ignore next -- DOM wiring; the unit-tested core is above */
function state() {
  return {
    address: "",
    plan: null,
    choices: new Map(),
    filter: "sweeping",
    threshold: 1,
    signed: 0,
    busy: false,
  };
}

/**
 * How often the entry re-reads which account the wallet is on, in ms.
 *
 * Polled rather than driven by an event because the wallet bundle publishes
 * exactly one - `asastats:swap-ready`, at bootstrap - and says nothing when a
 * reader connects, switches account or disconnects afterwards. `swap.js` lives
 * with that by re-reading at click time, which a button that must appear and
 * disappear cannot do. One property read a second is not a cost worth designing
 * around; a sweep entry that never appears because the reader connected after
 * the page loaded is.
 */
var CONNECTION_POLL_MS = 1000;

/**
 * Keep the address-page sweep entry pointed at the connected account.
 *
 * Only the address-page entry (`.dustsweep-toolbar`, one button whose account
 * this decides) is touched. The standalone sweep page lists the reader's
 * addresses as a directory with an account already on each button, and is not a
 * page they arrived at to read something else.
 *
 * The toolbar is also moved into `#id-dustsweep-slot` when the page offers one,
 * so the button sits with Historic data and CSV export rather than above the
 * page in a strip of its own. Moved rather than rendered there: this markup
 * arrives in an htmx partial, because it is the one per-reader thing on a page
 * whose cache entry is shared, and the partial has one mount point.
 *
 * @param {Element} root the `#id-dustsweep` container
 */
/* istanbul ignore next -- DOM wiring; sweepableAddress carries the decision */
function offerToConnectedAccount(root) {
  if (!root.classList.contains("dustsweep-toolbar")) return;

  var button = root.querySelector(".id-dustsweep-open");
  if (!button) return;
  var tag = button.querySelector(".dustsweep-open-address");
  var candidates = (root.dataset.addresses || "").split(/\s+/).filter(Boolean);

  var slot = document.getElementById("id-dustsweep-slot");
  if (slot && slot !== root.parentNode) slot.appendChild(root);

  var refresh = function () {
    var bridge = window.asastatsSwap;
    var active =
      bridge && typeof bridge.activeAddress === "function"
        ? bridge.activeAddress()
        : "";
    var address = sweepableAddress(candidates, active);
    if (address === button.dataset.address) return;

    button.dataset.address = address;
    if (tag) tag.textContent = shortAddress(address);
    root.hidden = !address;
  };

  refresh();
  whenSweepReady(refresh);
  window.setInterval(refresh, CONNECTION_POLL_MS);
}

/* istanbul ignore next -- DOM wiring */
function start() {
  var root = document.getElementById("id-dustsweep");
  var modal = document.getElementById("dustsweep-modal");
  if (!root || !modal) return;

  var planUrl = root.dataset.planUrl;
  var current = state();

  offerToConnectedAccount(root);

  root.querySelectorAll(".id-dustsweep-open").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!button.dataset.address) return;
      current = state();
      current.address = button.dataset.address;
      modal.querySelector(".id-dustsweep-address-tag").textContent =
        shortAddress(current.address);
      modal.showModal();
      reload(modal, planUrl, current);
    });
  });

  modal.querySelector(".id-dustsweep-close").addEventListener("click", function () {
    modal.close();
  });

  modal.querySelectorAll("[data-dustsweep-filter]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      current.filter = tab.dataset.dustsweepFilter;
      modal.querySelectorAll("[data-dustsweep-filter]").forEach(function (other) {
        other.setAttribute("aria-selected", String(other === tab));
      });
      renderLines(modal, current);
    });
  });

  var pop = modal.querySelector("#dustsweep-threshold-pop");
  modal
    .querySelector(".id-dustsweep-threshold-toggle")
    .addEventListener("click", function (event) {
      pop.hidden = !pop.hidden;
      event.currentTarget.setAttribute("aria-expanded", String(!pop.hidden));
    });

  modal.querySelectorAll(".id-dustsweep-threshold-preset").forEach(function (chip) {
    chip.addEventListener("click", function () {
      setThreshold(modal, current, Number(chip.dataset.threshold));
      reload(modal, planUrl, current);
    });
  });

  modal
    .querySelector(".id-dustsweep-threshold-custom")
    .addEventListener("change", function (event) {
      var typed = parseFloat(event.target.value);
      if (!isNaN(typed) && typed > 0) {
        setThreshold(modal, current, typed);
        reload(modal, planUrl, current);
      }
    });

  modal.querySelector(".id-dustsweep-cta").addEventListener("click", function () {
    sign(modal, planUrl, current);
  });
}

/* istanbul ignore next -- DOM wiring */
function setThreshold(modal, current, value) {
  current.threshold = value;
  modal.querySelector(".id-dustsweep-threshold-value").textContent =
    value + " ALGO";
  modal.querySelectorAll(".id-dustsweep-threshold-preset").forEach(function (chip) {
    chip.setAttribute(
      "aria-pressed",
      String(Number(chip.dataset.threshold) === value)
    );
  });
}

/* istanbul ignore next -- DOM wiring */
async function reload(modal, planUrl, current) {
  var cta = modal.querySelector(".id-dustsweep-cta");
  cta.disabled = true;
  cta.textContent = "Reading your holdings…";
  setNotice(modal, "");
  try {
    current.plan = await fetchPlan(planUrl, current.address, {
      threshold_algo: current.threshold,
      ...choicePayload(current.plan && current.plan.holdings, current.choices),
    });
    render(modal, current);
  } catch (error) {
    cta.textContent = "Nothing to sweep";
    setNotice(modal, error.message, true);
  }
}

/* istanbul ignore next -- DOM wiring */
function render(modal, current) {
  var plan = current.plan;
  var summary = modal.querySelector(".id-dustsweep-summary");
  summary.textContent = "";
  summaryFigures(plan).forEach(function (figure) {
    var cell = document.createElement("div");
    var term = document.createElement("dt");
    term.textContent = figure.label;
    var value = document.createElement("dd");
    value.textContent = figure.value;
    cell.append(term, value);
    summary.appendChild(cell);
  });

  renderLines(modal, current);

  var cta = modal.querySelector(".id-dustsweep-cta");
  cta.textContent = ctaLabel(plan);
  cta.disabled = !plan || !plan.next || current.busy;
  modal.querySelector(".id-dustsweep-why").textContent =
    (plan && plan.next && plan.next.why) || "";
  modal.querySelector(".id-dustsweep-progress").textContent = progressLabel(
    plan,
    current.signed
  );

  var degraded = degradedNotice(plan);
  if (degraded) setNotice(modal, degraded);
}

/**
 * Return the sentence explaining a plan that is thinner than it should be.
 *
 * **The evaluation outage is reported first, and says the more alarming thing**,
 * because it is the one a reader would otherwise misread as a fact about their
 * account rather than about the sweep. Somebody who sees three of their thirty
 * holdings offered needs to be told the sweep is degraded; being told only that
 * conversions are unavailable would explain the wrong half.
 *
 * @param {Object} plan the engine's answer
 * @returns {string} the notice, or "" when the plan is whole
 */
function degradedNotice(plan) {
  if (!plan) return "";

  if (plan.evaluation_unavailable) {
    return (
      "Your holdings could not be checked against this address's portfolio, " +
      "so only empty holdings are offered - nothing that still holds a " +
      "balance will be touched. " +
      plan.evaluation_unavailable
    );
  }

  if (plan.conversions_unavailable) {
    return (
      "Conversions are unavailable right now, so only close-outs are offered. " +
      plan.conversions_unavailable
    );
  }

  return "";
}

/* istanbul ignore next -- DOM wiring */
function renderLines(modal, current) {
  var panel = modal.querySelector(".id-dustsweep-panel");
  panel.textContent = "";
  var holdings = visibleLines(
    (current.plan && current.plan.holdings) || [],
    current.filter
  );

  if (!holdings.length) {
    var empty = document.createElement("p");
    empty.className = "dustsweep-empty";
    empty.textContent =
      current.filter === "all"
        ? "This address holds no assets."
        : "Nothing here is dust.";
    panel.appendChild(empty);
    return;
  }

  var list = document.createElement("ul");
  list.className = "dustsweep-lines";
  holdings.forEach(function (holding) {
    list.appendChild(renderLine(holding, current));
  });
  panel.appendChild(list);
}

/* istanbul ignore next -- DOM wiring */
function renderLine(holding, current) {
  var meta = DISPOSITIONS[holding.disposition];
  var row = document.createElement("li");
  row.className = "dustsweep-line";
  row.dataset.asset = String(holding.asset);

  // unit and id share one grid cell, so the row keeps its three columns
  var labels = assetLabels(holding);
  var named = document.createElement("span");
  named.className = "dustsweep-line-asset";
  var unit = document.createElement("span");
  unit.className = "dustsweep-line-unit";
  unit.textContent = labels.unit;
  var assetId = document.createElement("span");
  assetId.className = "dustsweep-line-id";
  assetId.textContent = labels.id;
  named.append(unit, assetId);

  var tone = badgeFor(holding);
  var badge = document.createElement("span");
  badge.className = "dustsweep-badge dustsweep-badge-" + tone.tone;
  badge.textContent = tone.label;

  var value = document.createElement("span");
  value.className = "dustsweep-line-value";
  value.textContent = holding.value === null ? "—" : algo(holding.value);

  var reason = document.createElement("span");
  reason.className = "dustsweep-line-reason";
  reason.textContent = holding.reason;

  row.append(named, badge, value, reason);

  if (meta) {
    var toggle = document.createElement("label");
    toggle.className = "dustsweep-line-toggle";
    var box = document.createElement("input");
    box.type = "checkbox";
    box.className = "dustsweep-line-include";
    box.checked = isIncluded(holding, current.choices);
    box.addEventListener("change", function () {
      current.choices.set(holding.asset, box.checked);
      current.dirty = true;
    });
    toggle.appendChild(box);
    row.insertBefore(toggle, value);
  }

  return row;
}

/* istanbul ignore next -- DOM wiring */
function setNotice(modal, text, isError) {
  var notice = modal.querySelector(".id-dustsweep-notice");
  notice.textContent = text || "";
  notice.classList.toggle("dustsweep-notice-error", Boolean(isError));
}

/* istanbul ignore next -- DOM wiring */
async function sign(modal, planUrl, current) {
  if (current.busy || !current.plan || !current.plan.next) return;

  // Signing is the only thing here that needs the wallet. The interface is
  // wired without it on purpose - a reader has to be able to open the sweep
  // and see what it would do *before* deciding to connect - so this is where
  // the bridge's absence is reported rather than at load.
  if (!window.asastatsSwap) {
    setNotice(modal, "Connect your wallet to sign this group.", true);
    return;
  }

  var cta = modal.querySelector(".id-dustsweep-cta");
  current.busy = true;
  cta.disabled = true;
  cta.textContent = "Check your wallet…";
  setNotice(modal, "");
  try {
    var txid = await signAction(
      current.plan.next,
      current.address,
      window.asastatsSwap
    );
    current.signed += 1;
    setNotice(modal, "Signed. Submitted as " + txid + ".");
    current.busy = false;
    await reload(modal, planUrl, current);
  } catch (error) {
    current.busy = false;
    setNotice(modal, error.message, true);
    render(modal, current);
  }
}

/**
 * Wire the interface, once the document has a body to wire.
 *
 * **Not gated on the wallet bridge.** It used to be, and the modal then never
 * opened for anybody who had not already connected: `whenSweepReady` waits for
 * `window.asastatsSwap`, which ships with the wallet bundle and is absent in a
 * bare browser. Reading what a sweep would do is exactly the thing a reader
 * wants before connecting, so the gate belongs on the signature and nowhere
 * else - see `sign`.
 */
/* istanbul ignore next -- DOM wiring */
function boot() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}

/* istanbul ignore else -- in the browser we self-start; under jest we export */
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    CLOSE_OUTS_PER_GROUP: CLOSE_OUTS_PER_GROUP,
    DISPOSITIONS: DISPOSITIONS,
    HOLDING_MINIMUM_BALANCE: HOLDING_MINIMUM_BALANCE,
    INERT: INERT,
    MAX_CLOSE_OUT_FEE: MAX_CLOSE_OUT_FEE,
    addressToBytes: addressToBytes,
    algo: algo,
    assetLabels: assetLabels,
    b64ToBytes: b64ToBytes,
    badgeFor: badgeFor,
    choicePayload: choicePayload,
    closeOutProblems: closeOutProblems,
    csrfToken: csrfToken,
    ctaLabel: ctaLabel,
    decodeMsgpack: decodeMsgpack,
    degradedNotice: degradedNotice,
    fetchPlan: fetchPlan,
    forfeitTargetProblems: forfeitTargetProblems,
    includedByDefault: includedByDefault,
    isActionable: isActionable,
    isIncluded: isIncluded,
    partialGroup: partialGroup,
    planLines: planLines,
    progressLabel: progressLabel,
    sameBytes: sameBytes,
    shortAddress: shortAddress,
    signAction: signAction,
    sweepableAddress: sweepableAddress,
    summarise: summarise,
    summaryFigures: summaryFigures,
    visibleLines: visibleLines,
    whenSweepReady: whenSweepReady,
  };
} else {
  boot();
}
