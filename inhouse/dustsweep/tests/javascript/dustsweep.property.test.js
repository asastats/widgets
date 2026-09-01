/**
 * Property tests for the browser control that decides what a user signs.
 *
 * **Why these exist.** `S1` came from a control certified by tests written in
 * the same commit as the code they certified, and the fixes for `S2` and `S3`
 * arrived the same way: new rules in the one place that gives a user's assets
 * away, with example cases chosen by whoever wrote the rules. Examples prove
 * the cases their author thought of. These state the invariants and let
 * fast-check look for the ones nobody did.
 *
 * **The transactions are real and the combinations are fuzzed.** `corpus.json`
 * is built by `make_corpus.py` with algosdk's own encoder, for the reason the
 * example suite gives: the decoder is being tested against Algorand's
 * canonical msgpack, and a generator emitting bytes directly would only test
 * it against someone's idea of that. What is generated here is the *group* and
 * the *description* -- which is where the interesting failures live, since `S2`
 * was a relationship between the two rather than a malformed transaction.
 *
 * Every property is a refusal. A counterexample is a group the control would
 * let through, which is the only failure here that costs anybody anything.
 */

const fc = require("fast-check");

const sweep = require("../../static/dustsweep/dustsweep.js");
const corpus = require("./corpus.json");
const mainnet = require("./mainnet-groups.json");

const NAMES = Object.keys(corpus.transactions);
const bytesFor = (name) => corpus.transactions[name];

/** Draw a group of 1..16 transactions, as names, so failures are readable. */
const groupNames = fc.array(fc.constantFrom(...NAMES), {
  minLength: 1,
  maxLength: 16,
});

/** Draw a plan line for one of the three assets the corpus uses. */
const describedLine = fc.record({
  asset: fc.constantFrom(
    corpus.emptyAsset,
    corpus.forfeitAsset,
    corpus.unlistedAsset
  ),
  amount: fc.constantFrom("0", "1000", 0, 1000),
  creator: fc.constantFrom(corpus.creator, corpus.stranger, corpus.owner, null),
});

const described = fc.array(describedLine, { maxLength: 4 });

/** Decode a corpus entry, for properties that need to look at its fields. */
function decode(name) {
  return sweep.decodeMsgpack(sweep.b64ToBytes(bytesFor(name)));
}

const problemsFor = (names, plan, address = corpus.owner) =>
  sweep.closeOutProblems(names.map(bytesFor), address, plan);

describe("closeOutProblems refuses every shape it promises to", () => {
  /**
   * Each of these names one rule and asserts it holds over every group and
   * every description, rather than over the one pairing the example suite
   * happens to use.
   */

  it("refuses any group containing a payment", () => {
    // The rule that matters most: a payment's `close` field drains the whole
    // ALGO balance, and it is the single most damaging thing that could hide
    // in a batch of sixteen.
    fc.assert(
      fc.property(groupNames, described, (names, plan) => {
        fc.pre(names.some((n) => decode(n).type === "pay"));
        return problemsFor(names, plan).length > 0;
      }),
      { numRuns: 400 }
    );
  });

  it("refuses any group containing a rekey", () => {
    fc.assert(
      fc.property(groupNames, described, (names, plan) => {
        fc.pre(names.some((n) => decode(n).rekey));
        return problemsFor(names, plan).length > 0;
      }),
      { numRuns: 400 }
    );
  });

  it("refuses any group that moves an amount", () => {
    // `asset_close_to` moves the whole balance by itself, so a sweep never
    // needs an amount -- and one that had it could send tokens somewhere the
    // close then does not.
    fc.assert(
      fc.property(groupNames, described, (names, plan) => {
        fc.pre(names.some((n) => decode(n).aamt));
        return problemsFor(names, plan).length > 0;
      }),
      { numRuns: 400 }
    );
  });

  it("refuses any group where a fee exceeds the cap", () => {
    fc.assert(
      fc.property(groupNames, described, (names, plan) => {
        fc.pre(
          names.some(
            (n) => (Number(decode(n).fee) || 0) > sweep.MAX_CLOSE_OUT_FEE
          )
        );
        return problemsFor(names, plan).length > 0;
      }),
      { numRuns: 400 }
    );
  });

  it("refuses any group over the protocol limit", () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(...NAMES), { minLength: 17, maxLength: 24 }),
        described,
        (names, plan) => problemsFor(names, plan).length > 0
      ),
      { numRuns: 200 }
    );
  });

  it("refuses everything when the address is unreadable", () => {
    fc.assert(
      fc.property(
        groupNames,
        described,
        fc.oneof(fc.string(), fc.constant(""), fc.constant("nope")),
        (names, plan, address) => problemsFor(names, plan, address).length > 0
      ),
      { numRuns: 300 }
    );
  });
});

describe("closeOutProblems only ever accepts a real close-out group", () => {
  /**
   * The converse, and the stronger statement: rather than listing what is
   * refused, this says what has to be true of anything accepted. A new rule
   * that accidentally weakened an old one would show up here even if no
   * refusal property named it.
   */
  it("accepting implies every transaction is a bounded, listed close-out", () => {
    fc.assert(
      fc.property(groupNames, described, (names, plan) => {
        if (problemsFor(names, plan).length) return true;

        const expected = {};
        (plan || []).forEach((one) => {
          expected[one.asset] =
            Number(one.amount) === 0 ? corpus.owner : one.creator;
        });

        return names.every((name) => {
          const txn = decode(name);
          return (
            txn.type === "axfer" &&
            !txn.aamt &&
            !txn.rekey &&
            txn.aclose &&
            (Number(txn.fee) || 0) <= sweep.MAX_CLOSE_OUT_FEE &&
            Object.prototype.hasOwnProperty.call(expected, String(txn.xaid)) &&
            sweep.sameBytes(
              txn.aclose,
              sweep.addressToBytes(expected[txn.xaid])
            )
          );
        });
      }),
      { numRuns: 600 }
    );
  });

  it("refuses a payment for a reason that names it a payment", () => {
    // Recorded from mutation testing, which is the only place it showed up:
    // disabling the `axfer` rule does *not* open a hole. A payment carries
    // `rcv`, not `arcv`, so it is still refused -- by "pays somebody else",
    // and a payment with `close_remainder_to` likewise. The type rule is
    // defence in depth, and what it actually buys is the message. That is
    // worth keeping and worth knowing it is what it is.
    const problems = sweep.closeOutProblems(
      [corpus.transactions.payment_draining_algo],
      corpus.owner,
      [{ asset: corpus.emptyAsset, amount: "0" }]
    );
    expect(problems[0]).toMatch(/is a pay, not an asset transfer/);
  });

  it("accepting a group of 16 is still possible, so the rules are not vacuous", () => {
    // A control that refused everything would satisfy every property above.
    const honest = new Array(16).fill("empty_close_to_self");
    expect(
      problemsFor(honest, [{ asset: corpus.emptyAsset, amount: "0" }])
    ).toEqual([]);
  });
});

describe("closeOutProblems never throws", () => {
  it("survives arbitrary base64 and arbitrary descriptions", () => {
    // It decodes bytes from the network. A throw here is an unhandled
    // rejection in `sign`, which shows the reader nothing at all.
    fc.assert(
      fc.property(
        fc.array(fc.string(), { maxLength: 6 }),
        fc.anything(),
        fc.oneof(fc.string(), fc.constant(corpus.owner)),
        (group, plan, address) => {
          const problems = sweep.closeOutProblems(group, address, plan);
          return Array.isArray(problems);
        }
      ),
      { numRuns: 500 }
    );
  });

  it("survives a description that is not a list of objects", () => {
    fc.assert(
      fc.property(groupNames, fc.anything(), (names, plan) =>
        Array.isArray(problemsFor(names, plan))
      ),
      { numRuns: 400 }
    );
  });
});

describe("forfeitTargetProblems fails closed", () => {
  /** A bridge whose `assetCreator` answers with `creator`. */
  const bridgeSaying = (creator) => ({ assetCreator: async () => creator });

  it("refuses whenever a forfeit is described and nothing can confirm it", async () => {
    await fc.assert(
      fc.asyncProperty(groupNames, described, async (names, plan) => {
        fc.pre(plan.some((one) => Number(one.amount) !== 0));
        const problems = await sweep.forfeitTargetProblems(
          names.map(bytesFor),
          plan,
          {}
        );
        return problems.length > 0;
      }),
      { numRuns: 300 }
    );
  });

  it("refuses whenever the chain cannot name a creator", async () => {
    await fc.assert(
      fc.asyncProperty(groupNames, described, async (names, plan) => {
        fc.pre(plan.some((one) => Number(one.amount) !== 0));
        fc.pre(
          names.some((n) =>
            plan.some(
              (one) =>
                Number(one.amount) !== 0 && decode(n).xaid === one.asset
            )
          )
        );
        const problems = await sweep.forfeitTargetProblems(
          names.map(bytesFor),
          plan,
          bridgeSaying(null)
        );
        return problems.length > 0;
      }),
      { numRuns: 300 }
    );
  });

  it("accepting implies every forfeited asset closed to the chain's creator", async () => {
    await fc.assert(
      fc.asyncProperty(groupNames, described, async (names, plan) => {
        const problems = await sweep.forfeitTargetProblems(
          names.map(bytesFor),
          plan,
          bridgeSaying(corpus.creator)
        );
        if (problems.length) return true;

        const forfeited = new Set(
          plan.filter((one) => Number(one.amount) !== 0).map((one) => one.asset)
        );
        return names.every((name) => {
          const txn = decode(name);
          if (!forfeited.has(txn.xaid)) return true;
          return sweep.sameBytes(
            txn.aclose,
            sweep.addressToBytes(corpus.creator)
          );
        });
      }),
      { numRuns: 400 }
    );
  });

  it("never throws, whatever the bridge does", async () => {
    await fc.assert(
      fc.asyncProperty(
        groupNames,
        fc.anything(),
        fc.oneof(
          fc.constant({}),
          fc.constant({ assetCreator: async () => corpus.creator }),
          fc.constant({
            assetCreator: async () => {
              throw new Error("network down");
            },
          }),
          fc.constant({ assetCreator: null }),
          fc.anything()
        ),
        async (names, plan, bridge) => {
          const problems = await sweep.forfeitTargetProblems(
            names.map(bytesFor),
            plan,
            bridge
          );
          return Array.isArray(problems);
        }
      ),
      { numRuns: 400 }
    );
  });
});

describe("the two checks together are what signAction runs", () => {
  it("a group either check refuses is never signed", async () => {
    await fc.assert(
      fc.asyncProperty(groupNames, described, async (names, plan) => {
        const bridge = {
          signAndSend: jest.fn().mockResolvedValue("TXID"),
          assetCreator: async () => corpus.creator,
        };
        const action = {
          kind: "close",
          transactions: names.map(bytesFor),
          holdings: plan,
        };

        try {
          await sweep.signAction(action, corpus.owner, bridge);
        } catch (error) {
          // Refused: the wallet must not have been asked for anything.
          return bridge.signAndSend.mock.calls.length === 0;
        }
        return bridge.signAndSend.mock.calls.length === 1;
      }),
      { numRuns: 300 }
    );
  });
});

describe("routedGroupProblems refuses rather than raises", () => {
  /**
   * `S6`'s guard runs over router groups, which carry application calls the
   * close-out rules never see. It is the one check with no `described` to
   * disagree with, so the invariants are about the bytes alone: it must never
   * throw, and it must never accept a group carrying a close or a rekey.
   */
  it("never raises, whatever the group is", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          groupNames.map((names) => names.map(bytesFor)),
          fc.anything(),
          fc.array(fc.anything(), { maxLength: 8 })
        ),
        (group) => {
          sweep.routedGroupProblems(group);
          return true;
        }
      ),
      { numRuns: 500 }
    );
  });

  it("accepting implies no transaction closes or rekeys", () => {
    // **Prefixed with a real guarded router call, or this proves nothing.**
    // `S7` made "calls no router method" a refusal, and no corpus transaction
    // is an application call - so without the prefix every generated group is
    // refused for that alone, the implication is vacuously true, and a group
    // that closed would never be examined. The prefix is transaction 2 of an
    // executed mainnet conversion, which is a `route` rather than one of the
    // two budget calls.
    const routerCall = mainnet.sweep_3_convert[2];
    expect(
      sweep.isBudgetOnlyCall(sweep.decodeMsgpack(sweep.b64ToBytes(routerCall)))
    ).toBe(false);

    let accepted = 0;
    fc.assert(
      fc.property(groupNames, (names) => {
        const group = [routerCall].concat(names.map(bytesFor));
        if (sweep.routedGroupProblems(group).length) return true;

        accepted += 1;
        return group.every((raw) => {
          const txn = sweep.decodeMsgpack(sweep.b64ToBytes(raw));
          return !txn.aclose && !txn.close && !txn.rekey;
        });
      }),
      { numRuns: 500 }
    );
    // Non-vacuity: some generated group really was accepted, so the
    // implication above was tested rather than merely satisfied.
    expect(accepted).toBeGreaterThan(0);
  });

  it("accepting implies the group calls a guarded router method", () => {
    fc.assert(
      fc.property(groupNames, (names) => {
        const group = names.map(bytesFor);
        if (sweep.routedGroupProblems(group).length) return true;

        return group.some((raw) => {
          const txn = sweep.decodeMsgpack(sweep.b64ToBytes(raw));
          return (
            txn.type === "appl" &&
            Number(txn.apid) === sweep.ROUTER_APP_ID &&
            !sweep.isBudgetOnlyCall(txn)
          );
        });
      }),
      { numRuns: 500 }
    );
  });
});
