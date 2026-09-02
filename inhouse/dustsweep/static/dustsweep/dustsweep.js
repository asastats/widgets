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
 * The most a routed group may pay the network, in microALGO.
 *
 * **The contract's number, mirrored rather than chosen.** `MAX_GROUP_FEE` in
 * `router_app.py` is 1,000,000 and `_assert_group_is_clean` totals the group
 * against it. Picking a different one here would mean refusing groups the
 * chain accepts, or accepting groups it will reject - both worse than being a
 * copy. Raise it there and this must follow, which is what the check named
 * after it in `verify-sweep.sh` is for.
 *
 * The seven groups in the audit's `evidence/` measure the headroom: the
 * dearest thing that has actually executed is a 13-transaction swap paying
 * 71,000, and the three convert groups pay 43,000 to 60,000. The ceiling is
 * fourteen times the worst of those, so it bounds a runaway without coming
 * near honest traffic.
 */
var MAX_GROUP_FEE = 1000000;

/**
 * The router application a conversion must actually call, on mainnet.
 *
 * **A default, not the only source.** The page supplies `data-router-app` and
 * that wins; this is what the check falls back to, so a missing attribute
 * cannot silently disable the rule. What matters either way is where it does
 * *not* come from: the plan response. An app id the engine supplied would make
 * this check agree with whatever the engine wanted, which is `S2` again.
 *
 * The contract has been redeployed twice already - `3688554446` is retired
 * and `3689591968` superseded - so this number has a lifetime. When it changes, a conversion refuses until
 * this is updated, which is the safe direction but a real outage; the
 * `data-router-app` override exists so a deployment can move first.
 */
var ROUTER_APP_ID = 3692588382;

/**
 * ARC-4 selectors for the two router methods that do **not** assert hygiene.
 *
 * `_assert_group_is_clean` runs from 13 of the contract's 15 entry points.
 * `verify_discount` and `pool_budget` are the exceptions - permissionless, no
 * state, no inner transactions - and the contract's own reasoning for exempting
 * them is that they ride alongside a `route` call which sweeps the group.
 *
 * That reasoning is why they cannot count here. A group of `pool_budget` plus
 * one hostile transfer calls the router, so a rule that asked only "does this
 * group call the router?" would pass it, and the guard the call was supposed
 * to bring would never run. So the check looks for a router call that is
 * *not* one of these.
 *
 * Computed from the method signatures rather than read off a group:
 * `verify_discount(byte[])void` and `pool_budget()void`, SHA-512/256, first
 * four bytes. `verify-sweep.sh` pins both against the contract.
 */
var BUDGET_ONLY_SELECTORS = [
  [0x93, 0xa1, 0xb8, 0x19], // verify_discount(byte[])void
  [0x9e, 0x57, 0xd6, 0x2c], // pool_budget()void
];

/** Return whether this transaction is one of the two exempt router calls. */
function isBudgetOnlyCall(txn) {
  var args = txn.apaa;
  if (!args || !args.length) return false;

  for (var i = 0; i < BUDGET_ONLY_SELECTORS.length; i++) {
    if (sameBytes(args[0], BUDGET_ONLY_SELECTORS[i])) return true;
  }
  return false;
}

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
 * How long a creator lookup may take before it counts as unanswered, in ms.
 *
 * **A hang was the one failure that neither refused nor accepted.** Every other
 * way `assetCreator` can fail already produces a refusal, but algosdk v3's
 * client sets no timeout of its own, so an unresponsive node left the reader on
 * a spinner with no signature prompt and no error - the sweep neither happening
 * nor visibly failing. Ten seconds is far past a healthy round trip and short
 * enough that the refusal arrives while the reader is still watching.
 */
var CREATOR_LOOKUP_TIMEOUT = 10000;

/**
 * Resolve `promise`, or `null` if it takes longer than `ms`.
 *
 * Null rather than a rejection deliberately: the caller already treats "no
 * creator" as a refusal, so a timeout joins the unreachable node and the
 * unreadable asset instead of opening a fourth path.
 *
 * @param {Promise} promise the lookup in flight
 * @param {number} ms how long to wait
 * @returns {Promise<*>} what it resolved to, or null on timeout
 */
function withTimeout(promise, ms) {
  var timer;
  var settled = function (value) {
    clearTimeout(timer);
    return value;
  };
  return Promise.race([
    Promise.resolve(promise).then(settled, function (error) {
      clearTimeout(timer);
      throw error;
    }),
    new Promise(function (resolve) {
      timer = setTimeout(function () {
        resolve(null);
      }, ms);
    }),
  ]);
}

/**
 * Return whether the plan says this holding is forfeited rather than empty.
 *
 * **One function because two callers must never disagree.** The safety of the
 * whole forfeit check rests on an invariant that spans both of them: a
 * transaction may close to an address other than the sweeper's *only* when
 * this returns true, and this returning true is *also* what sends the
 * destination to the chain to be confirmed. `closeOutProblems` picks the
 * expected target with it; `forfeitTargetProblems` picks what to look up with
 * it. Written out twice, the two could drift - a later `> 0`, or a
 * `disposition` field consulted in one place - and a forfeit would quietly
 * stop being confirmed against anything. That is `S2` reopening silently,
 * with every test still passing, which is why the predicate has a name.
 *
 * It pairs with `planLines` rather than repeating its work: that one decides
 * which lines are readable at all, this one decides what a readable line
 * means.
 *
 * @param {Object} holding one of the lines `planLines` kept
 * @returns {boolean} true when closing it gives tokens away
 */
function isForfeit(holding) {
  return Number(holding.amount) !== 0;
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
 * - **the fee is bounded**, per transaction. Nothing else bounds it: the engine
 *   sets it from the node's suggested parameters and the bridge preserves
 *   whatever arrives. Mainnet will take a fee up to the account's entire
 *   spendable balance, so a sweep that emptied an account without moving a
 *   single token was a valid group. There is deliberately no whole-group rule
 *   to go with this one; `MAX_CLOSE_OUT_FEE` explains why it would be dead
 *   code rather than a second line of defence.
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
    expected[one.asset] = isForfeit(one) ? one.creator : address;
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
          algo(MAX_CLOSE_OUT_FEE) + " ALGO"
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
 * *that*. One lookup per distinct asset, all issued together, and only for
 * holdings `isForfeit` says still carry a balance - an empty holding closes to
 * the connected account, which was never in doubt. That predicate is shared
 * with `closeOutProblems` rather than repeated, because a forfeit that stops
 * matching it here stops being confirmed against anything.
 *
 * **It fails closed.** A bridge too old to expose `assetCreator`, an
 * unreachable node, an asset whose parameters cannot be read, and a node that
 * never answers at all - see `CREATOR_LOOKUP_TIMEOUT` - all produce a problem
 * rather than a pass. Refusing to sign costs a reader one sweep;
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
    if (isForfeit(one)) forfeited[one.asset] = true;
  });
  if (!Object.keys(forfeited).length) return [];

  if (!bridge || typeof bridge.assetCreator !== "function") {
    return [
      "this wallet connection cannot confirm who an asset's creator is, and " +
        "the sweep will not give a holding away on the engine's word alone",
    ];
  }

  // Decoded once, up front, so the lookups can be issued together below. A
  // transaction that will not decode is left as null: `closeOutProblems` has
  // already refused this group over it.
  var decoded = (Array.isArray(encoded) ? encoded : []).map(function (raw) {
    try {
      return decodeMsgpack(b64ToBytes(raw));
    } catch (error) {
      return null;
    }
  });

  // **One round trip, not one per asset.** The lookups are independent and
  // already at most one per distinct asset; awaiting them in the compare loop
  // made a group of sixteen forfeits wait sixteen times the node's latency
  // before the wallet prompt opened. A rejection folds to null here so the
  // "could not be confirmed" branch below stays the single refusal path.
  var wanted = [];
  decoded.forEach(function (txn) {
    if (txn && forfeited[txn.xaid] && wanted.indexOf(txn.xaid) < 0) {
      wanted.push(txn.xaid);
    }
  });
  var resolved = {};
  await Promise.all(
    wanted.map(async function (xaid) {
      try {
        resolved[xaid] = await withTimeout(
          bridge.assetCreator(xaid),
          CREATOR_LOOKUP_TIMEOUT
        );
      } catch (error) {
        resolved[xaid] = null;
      }
    })
  );

  var problems = [];
  for (var index = 0; index < decoded.length; index++) {
    var txn = decoded[index];
    if (!txn || !forfeited[txn.xaid]) continue;

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

/**
 * Return every reason this routed group is not one a router would build.
 *
 * **`_assert_group_is_clean`, mirrored in the browser.** The contract already
 * refuses a rekey, a `close_remainder_to`, an `asset_close_to` and a group fee
 * over `MAX_GROUP_FEE`, over the whole group, from 13 of its 15 entry points.
 * That guard is real, deployed and immutable, and this is a copy of it rather
 * than a second opinion about it: mirroring cannot refuse a group the contract
 * would accept.
 *
 * **What the copy buys is that it runs.** An assertion inside an application
 * only executes if the application is called, and nothing off-chain required a
 * conversion group to call the router. `signAction` chose whether to inspect a
 * group by reading `action.kind` from the same response that carried the
 * bytes, so a group labelled `convert` reached the wallet unexamined - by the
 * widget, which skipped it, and by the contract, which was never in the group
 * to object. That was the audit's `S6`, and it is the same shape as `S2` moved
 * up a level: `S2` was a reference value the engine supplied, this was the
 * switch deciding whether any checking happened at all.
 *
 * So the rule is applied to the bytes, whatever the response calls them, and
 * `action.kind` stops being a security decision.
 *
 * **Why the decoder is up to it.** It reads the msgpack subset a *close-out*
 * uses, and a routed group carries application calls - larger, and carrying
 * argument and foreign-asset arrays a close-out never has. Run over the 97
 * transactions in the audit's `evidence/`, every one of which executed on
 * mainnet, it decodes all 97: the tags they use are `fixmap`, `fixarray`,
 * `fixstr`, `bin8` and `uint16/32/64`, all of them already supported. A
 * transaction that will not decode is refused rather than skipped, so a tag
 * that does turn up costs a conversion instead of passing one through.
 *
 * @param {Array<string>} encoded base64 msgpack transactions, in group order
 * @param {number|string} [routerApp] the router application id to require
 * @returns {Array<string>} problems, empty when the group is clean
 */
function routedGroupProblems(encoded, routerApp) {
  if (!Array.isArray(encoded) || encoded.length === 0) {
    return ["the group carries no transactions"];
  }

  var router = Number(routerApp) || ROUTER_APP_ID;
  var problems = [];
  var guarded = false;
  var paid = 0;
  encoded.forEach(function (raw, index) {
    var where = "transaction " + (index + 1) + " ";
    var txn;
    try {
      txn = decodeMsgpack(b64ToBytes(raw));
    } catch (error) {
      problems.push(where + "could not be decoded");
      return;
    }

    if (!txn || typeof txn !== "object") {
      problems.push(where + "could not be decoded");
      return;
    }

    paid += Number(txn.fee) || 0;
    if (txn.rekey) problems.push(where + "rekeys the account");
    if (txn.close) problems.push(where + "closes the account");
    if (txn.aclose) problems.push(where + "closes a holding");

    if (
      txn.type === "appl" &&
      Number(txn.apid) === router &&
      !isBudgetOnlyCall(txn)
    ) {
      guarded = true;
    }
  });

  // **The rule that puts the contract back in the group.** Everything above is
  // the hygiene half of `_assert_group_is_clean`, and hygiene is not what a
  // conversion needs checking for: a plain transfer of the whole balance to a
  // stranger carries no close, no rekey and an ordinary fee. What refuses that
  // is the router's own logic - the input proven spent, the co-signed floor,
  // the pairwise-distinct assets - and none of it runs unless the router is
  // called. This is the audit's `S7`: mirroring the guard duplicated the half
  // that was already cheap and left the half that was load-bearing.
  if (!guarded) {
    problems.push(
      "the group calls no router method that would check it, so nothing on " +
        "chain will refuse what it does"
    );
  }

  // Totalled rather than checked per transaction, for the reason the contract
  // gives: the total is what a signer loses, and it is the bound that survives
  // the builder redistributing fees across the group, which it already does.
  if (paid > MAX_GROUP_FEE) {
    problems.push(
      "the group pays " + algo(paid) + " ALGO in fees, over the limit of " +
        algo(MAX_GROUP_FEE) + " ALGO"
    );
  }

  return problems;
}

/**
 * Return every reason this routed group spends something the plan did not name.
 *
 * **`S8`'s Mitigation 1: bind the moved assets to what the plan described.**
 * `routedGroupProblems` asks whether a group is *hygienic* and whether the
 * router is in it to check it. It never asks whether the group does what the
 * reader was shown, because it is not given the plan - so a conversion
 * described as "convert BUSK, worth 0.0016 ALGO" could sell five thousand USDC
 * and be accepted. The close-out path refuses exactly that substitution
 * ("closes asset N, which was not listed"); this is the same rule for the
 * other half.
 *
 * **It does not close `S8`.** A compromised engine can still add a transfer
 * *alongside* a route, because that transfer moves an asset the plan does
 * name. What this stops is the substitution: the described trade being a
 * different trade. The audit is explicit that the two are separate and that
 * this one is worth taking on its own.
 *
 * **Only what the connected account sends is judged**, and that is the whole
 * of the rule. A route's other transactions are the quote signer's
 * authorisation and the pools' payouts back to the reader; neither is the
 * reader's to constrain, and refusing them would refuse every honest group.
 * Checked against the seven executed mainnet groups in the audit's
 * `evidence/`: in each, every transfer the holder sends moves the *same* asset
 * - the input, split one transfer per venue - and the parts sum to exactly the
 * holding the plan described. `sweep_3_convert` sends 1,109,201 + 226,771 +
 * 7,961,066 + 5,936,931 of asset 796425061, which is 15,233,969, which is that
 * address's whole COOP balance.
 *
 * A zero-amount transfer is left alone: that is an opt-in, which a route needs
 * and which moves nothing. It cannot hide a close-out, because
 * `routedGroupProblems` refuses any `aclose` in the group.
 *
 * **A separate function rather than another argument to
 * `routedGroupProblems`.** An optional parameter that silently disables a rule
 * when a caller forgets it is the exact failure this file has already had once
 * - see `state`, where `data-router-app` was assembled and then dropped. A
 * missing call here is visible in `signAction`.
 *
 * @param {Array<string>} encoded base64 msgpack transactions, in group order
 * @param {string} address the account being swept
 * @param {Array<Object>} described the plan's holdings for this group
 * @returns {Array<string>} problems, empty when the group spends what it said
 */
function convertedInputProblems(encoded, address, described) {
  var owner = addressToBytes(address);
  if (!owner) return ["the address being swept is unreadable"];

  var allowed = {};
  planLines(described).forEach(function (one) {
    var amount = Number(one.amount);
    allowed[one.asset] = isFinite(amount) && amount > 0 ? amount : 0;
  });

  var problems = [];
  var moved = {};
  (Array.isArray(encoded) ? encoded : []).forEach(function (raw, index) {
    var where = "transaction " + (index + 1) + " ";
    var txn;
    try {
      txn = decodeMsgpack(b64ToBytes(raw));
    } catch (error) {
      // `routedGroupProblems` has already refused the group over this
      return;
    }

    if (!txn || typeof txn !== "object" || !sameBytes(txn.snd, owner)) return;

    var asset = txn.type === "pay" ? ALGO_ASSET : txn.xaid;
    var amount = Number(txn.type === "pay" ? txn.amt : txn.aamt) || 0;
    if (!amount) return;

    if (!Object.prototype.hasOwnProperty.call(allowed, asset)) {
      problems.push(
        where + "spends asset " + asset + ", which this conversion did not name"
      );
      return;
    }

    moved[asset] = (moved[asset] || 0) + amount;
  });

  Object.keys(moved).forEach(function (asset) {
    if (moved[asset] > allowed[asset]) {
      problems.push(
        "the group spends " + moved[asset] + " of asset " + asset +
          ", more than the " + allowed[asset] + " this conversion described"
      );
    }
  });

  return problems;
}

/** ALGO, which a `pay` moves and which has no asset id of its own. */
var ALGO_ASSET = 0;

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

/**
 * Return where this holding's tokens go, for the reader to see before signing.
 *
 * **The audit's `S2` recommendation 2.** The row showed unit, id, badge, value
 * and reason, and never the address the tokens went to - so on the one
 * disposition that gives something away, the destination was the single fact
 * the reader was not shown. `forfeitTargetProblems` now confirms that address
 * against the chain, which is the control; this is the disclosure, and the
 * audit is explicit that it is a complement rather than a substitute. A reader
 * who can see the creator can compare it with the wallet prompt; one who
 * cannot is trusting two systems instead of checking one.
 *
 * **Shortened, with the whole address kept for the title.** A 58-character
 * address on every line is why this was not done the first time. The short
 * form is enough to compare against a wallet prompt at a glance, and the full
 * one is a hover or a copy away.
 *
 * Only a forfeit names somebody else. A close returns the holding to the
 * account it is already in, which is worth saying plainly rather than leaving
 * blank - "nothing leaves this account" is the reassurance a reader wants -
 * and a conversion has no close target at all, so it gets nothing.
 *
 * @param {Object} holding a plan line
 * @returns {{text: string, title: string}} empty text when there is nothing to say
 */
function destinationLabel(holding) {
  if (!holding) return { text: "", title: "" };

  if (holding.disposition === "forfeit") {
    var creator = holding.creator;
    if (!creator) return { text: "to an unnamed address", title: "" };

    return { text: "to " + shortAddress(creator), title: creator };
  }

  if (holding.disposition === "close") {
    return { text: "stays in this account", title: "" };
  }

  return { text: "", title: "" };
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
 * through `signAndSend`.
 *
 * **Both paths are inspected, and that is the fix for `S6`.** This used to
 * inspect only the close-out one, on the reasoning that a conversion carries a
 * router call the contract itself checks. Every honest conversion does. But
 * `action.kind` is a field of the same response as the bytes, so the engine
 * chose which branch ran - and a group labelled `convert` that contained no
 * application call was refused by nobody: not by this function, which returned
 * early, and not by `_assert_group_is_clean`, which cannot refuse a group that
 * never calls the contract. `routedGroupProblems` mirrors that guard here so
 * the answer no longer depends on what the response calls the group.
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
 * @param {number|string} [routerApp] router app id, from `data-router-app`
 * @returns {Promise<string>} the submitted transaction id
 */
async function signAction(action, address, bridge, routerApp) {
  if (action.kind === "convert") {
    if (typeof bridge.signAndSendPartial !== "function") {
      throw new Error("The connected wallet does not support quote-signed groups");
    }

    var routed = routedGroupProblems(action.transactions, routerApp);
    if (!routed.length) {
      // Only once the group is hygienic and the router is in it to check it.
      // This asks the other question - whether the group spends what the
      // reader was shown - which is `S8`'s Mitigation 1.
      routed = convertedInputProblems(
        action.transactions,
        address,
        action.holdings
      );
    }
    if (routed.length) {
      throw new Error("This group was refused: " + routed.join("; "));
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
 * Return the four figures the summary strip shows.
 *
 * `recoverable` is the minimum balance alone, net of fees - the certain half.
 * The planner subtracts them there (`sweep.py`: `(closes + conversions) *
 * HOLDING_MINIMUM_BALANCE - fees`). A close returns exactly 0.1 ALGO whatever
 * the token is worth, while conversion proceeds depend on quotes not taken
 * yet, and promising the uncertain half up front is how a sweep ends up having
 * under-delivered.
 *
 * **Fees are shown, not folded away.** `summary.fees` was computed by the
 * planner and sent here from the beginning, and nothing rendered it: there was
 * no number on this screen that would have moved if every fee in the group had
 * been a thousand times larger, which is the reporting half of the audit's
 * `S3`. It sits beside what the sweep returns because the two are the same
 * arithmetic.
 *
 * **It reports; it does not verify.** Both figures are the planner's, and a
 * sweep spans several groups while this widget only ever holds the bytes of
 * the next one - so there is nothing here to check the total against, and a
 * planner that reported zero fees would render "0.00 ALGO" unchallenged. The
 * row is honest reporting, not a control: what bounds what a reader can lose
 * is `MAX_CLOSE_OUT_FEE`, applied to the bytes about to be signed. Read it as
 * telling a reader when an honest sweep is not worth signing.
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

/**
 * Return a fresh interface state, carrying the page context it must not lose.
 *
 * **`routerApp` is a parameter rather than an assignment afterwards.** It used
 * to be one: `start` built a state, set `current.routerApp` on it, and then the
 * open handler replaced the whole object with a fresh `state()` before the
 * modal was ever shown. So `routedGroupProblems` was called with `undefined`
 * on every conversion any reader ever signed, fell back to the built-in
 * `ROUTER_APP_ID`, and `data-router-app` did nothing at all.
 *
 * That is the escape hatch for a redeployment, and its whole purpose is to let
 * the deployment move before this file does - so the failure it was there to
 * prevent is exactly the one that would happen: the router is redeployed, the
 * built-in id goes stale, and every conversion is refused with "the group
 * calls no router method that would check it" until the JavaScript is updated.
 * Safe direction, real outage, and the mechanism to avoid it was disconnected.
 *
 * Taking it as an argument is what stops the same omission recurring quietly:
 * a caller that forgets it now passes `undefined` visibly at the call site
 * rather than dropping a key from an object literal.
 *
 * @param {string} [routerApp] the page's `data-router-app`
 * @returns {Object} the interface state
 */
function state(routerApp) {
  return {
    address: "",
    plan: null,
    choices: new Map(),
    filter: "sweeping",
    threshold: 1,
    signed: 0,
    busy: false,
    routerApp: routerApp,
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
  // Page context, not plan response: `routedGroupProblems` falls back to the
  // built-in id, so a missing attribute cannot turn the rule off.
  var current = state(root.dataset.routerApp);

  offerToConnectedAccount(root);

  root.querySelectorAll(".id-dustsweep-open").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!button.dataset.address) return;
      // the reset that used to drop `routerApp` - see `state`
      current = state(root.dataset.routerApp);
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

  // `S2` recommendation 2: on a forfeit this is the address the tokens leave
  // for, and it used to be the one fact the row did not carry.
  var going = destinationLabel(holding);
  if (going.text) {
    var destination = document.createElement("span");
    destination.className = "dustsweep-line-destination";
    destination.textContent = going.text;
    if (going.title) destination.title = going.title;
    row.append(destination);
  }

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
      window.asastatsSwap,
      current.routerApp
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
    CREATOR_LOOKUP_TIMEOUT: CREATOR_LOOKUP_TIMEOUT,
    MAX_CLOSE_OUT_FEE: MAX_CLOSE_OUT_FEE,
    MAX_GROUP_FEE: MAX_GROUP_FEE,
    ROUTER_APP_ID: ROUTER_APP_ID,
    addressToBytes: addressToBytes,
    algo: algo,
    assetLabels: assetLabels,
    b64ToBytes: b64ToBytes,
    badgeFor: badgeFor,
    choicePayload: choicePayload,
    closeOutProblems: closeOutProblems,
    convertedInputProblems: convertedInputProblems,
    csrfToken: csrfToken,
    ctaLabel: ctaLabel,
    decodeMsgpack: decodeMsgpack,
    destinationLabel: destinationLabel,
    degradedNotice: degradedNotice,
    fetchPlan: fetchPlan,
    forfeitTargetProblems: forfeitTargetProblems,
    includedByDefault: includedByDefault,
    isActionable: isActionable,
    isBudgetOnlyCall: isBudgetOnlyCall,
    isForfeit: isForfeit,
    routedGroupProblems: routedGroupProblems,
    withTimeout: withTimeout,
    isIncluded: isIncluded,
    partialGroup: partialGroup,
    planLines: planLines,
    progressLabel: progressLabel,
    sameBytes: sameBytes,
    shortAddress: shortAddress,
    signAction: signAction,
    state: state,
    sweepableAddress: sweepableAddress,
    summarise: summarise,
    summaryFigures: summaryFigures,
    visibleLines: visibleLines,
    whenSweepReady: whenSweepReady,
  };
} else {
  boot();
}
