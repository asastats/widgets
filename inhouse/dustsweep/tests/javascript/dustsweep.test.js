/**
 * Does the sweep controller refuse a group that is not what it was described as?
 *
 * That is the only question here worth much. A close-out group is sixteen
 * transactions approved with one click, and `asset_close_to` moves an entire
 * balance - so the tests below are mostly attempts to slip something past
 * `closeOutProblems`, each one a transaction that is perfectly well-formed and
 * not what the plan said.
 *
 * **The fixtures are real.** Every base64 string was produced by algosdk's own
 * encoder rather than assembled by hand, because the decoder is being tested
 * against Algorand's canonical msgpack and a hand-rolled fixture would only
 * test it against my idea of that.
 */

const sweep = require("../../static/dustsweep/dustsweep.js");

const ADDRESS = "OGRUNXPSMO7Z7EGOGONA7BVEIN7YIJZZB372GZGJIAPB363C6KB42CEN2M";
const CREATOR = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU";

// Encoded by algosdk. Each is a complete, valid Algorand transaction.
const CLOSE_TO_SELF =
  "iaZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkBQ==";
const FORFEIT_TO_CREATOR =
  "iaZhY2xvc2XEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3pGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkCQ==";
const WITH_AMOUNT =
  "iqRhYW10B6ZhY2xvc2XEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3pGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkBQ==";
const WITH_REKEY =
  "iqZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPppXJla2V5xCDRKmzwJnSXtPuUwMmg0NNsw5zlaO8rSEG5yvAhuGvG96NzbmTEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpHR5cGWlYXhmZXKkeGFpZAU=";
const TO_STRANGER =
  "iaZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3o2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkBQ==";
const NO_CLOSE =
  "iKRhcmN2xCBxo0bd8mO/n5DOM5oPhqRDf4QnOQ7/o2TJQB4d+2Lyg6NmZWXNA+iiZnYBomdoxCDAYcTY/B293tLXYEvkVo4/bQQZh6w3veS2ILWrOSSK36Jsds0D6aNzbmTEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpHR5cGWlYXhmZXKkeGFpZAU=";
const PAYMENT_DRAIN =
  "iKVjbG9zZcQg0Sps8CZ0l7T7lMDJoNDTbMOc5WjvK0hBucrwIbhrxvejZmVlzQPoomZ2AaJnaMQgwGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit+ibHbNA+mjcmN2xCBxo0bd8mO/n5DOM5oPhqRDf4QnOQ7/o2TJQB4d+2Lyg6NzbmTEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpHR5cGWjcGF5";
const WRONG_ASSET =
  "iaZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkzQPn";

const WRONG_SENDER =
  "iaZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0D6KJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQg0Sps8CZ0l7T7lMDJoNDTbMOc5WjvK0hBucrwIbhrxvekdHlwZaVheGZlcqR4YWlkBQ==";

// Fee fixtures for `S3`. Identical to FORFEIT_TO_CREATOR but for the fee, so
// anything they are refused for is the fee and nothing else.
const FAT_FEE =
  "iaZhY2xvc2XEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3pGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc4ATEtAomZ2AaJnaMQgwGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit+ibHbNA+mjc25kxCBxo0bd8mO/n5DOM5oPhqRDf4QnOQ7/o2TJQB4d+2Lyg6R0eXBlpWF4ZmVypHhhaWQJ";
const AT_FEE_LIMIT =
  "iaZhY2xvc2XEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3pGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0nEKJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkCQ==";
const OVER_FEE_LIMIT =
  "iaZhY2xvc2XEINEqbPAmdJe0+5TAyaDQ02zDnOVo7ytIQbnK8CG4a8b3pGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc0nEaJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkCQ==";
/** Asset 5 closing to self with the fee omitted, as a zero fee is encoded. */
const ZERO_FEE =
  "iKZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDomZ2AaJnaMQgwGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit+ibHbNA+mjc25kxCBxo0bd8mO/n5DOM5oPhqRDf4QnOQ7/o2TJQB4d+2Lyg6R0eXBlpWF4ZmVypHhhaWQF";
/** Asset 5 closing to self, fee 0.05 ALGO - half of what the close returns. */
const HALF_MBR_FEE =
  "iaZhY2xvc2XEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDpGFyY3bEIHGjRt3yY7+fkM4zmg+GpEN/hCc5Dv+jZMlAHh37YvKDo2ZlZc3DUKJmdgGiZ2jEIMBhxNj8Hb3e0tdgS+RWjj9tBBmHrDe95LYgtas5JIrfomx2zQPpo3NuZMQgcaNG3fJjv5+QzjOaD4akQ3+EJzkO/6NkyUAeHfti8oOkdHlwZaVheGZlcqR4YWlkBQ==";

/** The plan lines matching the two well-formed fixtures above. */
const EMPTY_HOLDING = { asset: 5, amount: "0", creator: CREATOR };
const FORFEITED_HOLDING = { asset: 9, amount: "1000", creator: CREATOR };

describe("decodeMsgpack", () => {
  test("reads the fields a close-out is judged on", () => {
    const txn = sweep.decodeMsgpack(sweep.b64ToBytes(FORFEIT_TO_CREATOR));
    expect(txn.type).toBe("axfer");
    expect(txn.xaid).toBe(9);
    expect(txn.aclose).toHaveLength(32);
    expect(txn.snd).toHaveLength(32);
  });

  test("omits fields at their zero value, as canonical encoding does", () => {
    // The amount is absent rather than present-and-zero, which is why the
    // whitelist tests `txn.aamt` for truthiness rather than for equality.
    const txn = sweep.decodeMsgpack(sweep.b64ToBytes(CLOSE_TO_SELF));
    expect(txn.aamt).toBeUndefined();
    expect(txn.rekey).toBeUndefined();
  });

  test("reads a multi-byte asset id", () => {
    const txn = sweep.decodeMsgpack(sweep.b64ToBytes(WRONG_ASSET));
    expect(txn.xaid).toBe(999);
  });

  test("reads every integer width", () => {
    // 0x7f fixint, 0xcc uint8, 0xcd uint16, 0xce uint32, 0xcf uint64
    const encoded = new Uint8Array([
      0x85,
      0xa1, 0x61, 0x7f,
      0xa1, 0x62, 0xcc, 0xff,
      0xa1, 0x63, 0xcd, 0x01, 0x00,
      0xa1, 0x64, 0xce, 0x00, 0x01, 0x00, 0x00,
      0xa1, 0x65, 0xcf, 0, 0, 0, 0, 0, 0, 0x01, 0x00,
    ]);
    expect(sweep.decodeMsgpack(encoded)).toEqual({
      a: 127,
      b: 255,
      c: 256,
      d: 65536,
      e: 256,
    });
  });

  test("reads the remaining container and literal tags", () => {
    const encoded = new Uint8Array([
      0x84,
      0xa1, 0x61, 0x90 + 2, 0xc0, 0xc2,
      0xa1, 0x62, 0xc3,
      0xa1, 0x63, 0xc4, 0x02, 0xaa, 0xbb,
      0xa1, 0x64, 0xd9, 0x03, 0x66, 0x6f, 0x6f,
    ]);
    const decoded = sweep.decodeMsgpack(encoded);
    expect(decoded.a).toEqual([null, false]);
    expect(decoded.b).toBe(true);
    expect(Array.from(decoded.c)).toEqual([0xaa, 0xbb]);
    expect(decoded.d).toBe("foo");
  });

  test("reads the wide container and binary tags", () => {
    // map16, array16, str16, bin16 and bin32 - reachable in principle and
    // cheap to support, so they are supported rather than left to throw.
    const encoded = new Uint8Array([
      0xde, 0x00, 0x03,
      0xa1, 0x61, 0xdc, 0x00, 0x01, 0x2a,
      0xa1, 0x62, 0xda, 0x00, 0x02, 0x68, 0x69,
      0xa1, 0x63, 0xc5, 0x00, 0x01, 0x07,
    ]);
    const decoded = sweep.decodeMsgpack(encoded);
    expect(decoded.a).toEqual([42]);
    expect(decoded.b).toBe("hi");
    expect(Array.from(decoded.c)).toEqual([7]);
    expect(
      Array.from(
        sweep.decodeMsgpack(new Uint8Array([0xc6, 0, 0, 0, 1, 0x09]))
      )
    ).toEqual([9]);
  });

  test("throws on a tag it does not support rather than guessing", () => {
    // 0xd0 is int8. A decoder that quietly returned something for an
    // unsupported tag could mis-read a field the whitelist then approves.
    expect(() => sweep.decodeMsgpack(new Uint8Array([0xd0, 0x01]))).toThrow(
      /unsupported msgpack tag/
    );
  });
});

describe("addressToBytes", () => {
  test("returns the 32 public-key bytes", () => {
    expect(sweep.addressToBytes(ADDRESS)).toHaveLength(32);
  });

  test("matches what the transaction carries", () => {
    const txn = sweep.decodeMsgpack(sweep.b64ToBytes(CLOSE_TO_SELF));
    expect(sweep.sameBytes(txn.snd, sweep.addressToBytes(ADDRESS))).toBe(true);
  });

  test.each([null, undefined, 42, "", "TOOSHORT", ADDRESS + "A"])(
    "returns null for %p rather than throwing",
    (bad) => {
      expect(sweep.addressToBytes(bad)).toBeNull();
    }
  );

  test("returns null when a character is not base32", () => {
    expect(sweep.addressToBytes("1".repeat(58))).toBeNull();
  });
});

describe("sameBytes", () => {
  test("is false for anything missing or of a different length", () => {
    expect(sweep.sameBytes(null, new Uint8Array(1))).toBe(false);
    expect(sweep.sameBytes(new Uint8Array(1), null)).toBe(false);
    expect(sweep.sameBytes(new Uint8Array(1), new Uint8Array(2))).toBe(false);
  });

  test("compares content, not identity", () => {
    expect(sweep.sameBytes(new Uint8Array([1, 2]), new Uint8Array([1, 2]))).toBe(
      true
    );
    expect(sweep.sameBytes(new Uint8Array([1, 2]), new Uint8Array([1, 3]))).toBe(
      false
    );
  });
});

describe("closeOutProblems accepts what the plan described", () => {
  test("an empty holding closing to itself", () => {
    expect(
      sweep.closeOutProblems([CLOSE_TO_SELF], ADDRESS, [EMPTY_HOLDING])
    ).toEqual([]);
  });

  test("a forfeit closing to the asset's creator", () => {
    expect(
      sweep.closeOutProblems([FORFEIT_TO_CREATOR], ADDRESS, [FORFEITED_HOLDING])
    ).toEqual([]);
  });

  test("both together, which is what a real group looks like", () => {
    expect(
      sweep.closeOutProblems(
        [CLOSE_TO_SELF, FORFEIT_TO_CREATOR],
        ADDRESS,
        [EMPTY_HOLDING, FORFEITED_HOLDING]
      )
    ).toEqual([]);
  });
});

describe("closeOutProblems refuses what it was not described as", () => {
  test("a payment, which could drain the whole ALGO balance", () => {
    // The single most damaging thing that could hide in a batch of sixteen:
    // `close_remainder_to` sends every microALGO the account holds.
    const problems = sweep.closeOutProblems([PAYMENT_DRAIN], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toMatch(/is a pay, not an asset transfer/);
  });

  test("a transfer that moves an amount", () => {
    const problems = sweep.closeOutProblems([WITH_AMOUNT], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toContain(
      "transaction 1 moves an amount rather than closing"
    );
  });

  test("a rekey, which hands the account away permanently", () => {
    const problems = sweep.closeOutProblems([WITH_REKEY], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toContain("transaction 1 rekeys the account");
  });

  test("a transfer sent by somebody else", () => {
    // Would fail at signing anyway - the wallet holds one key - but a group
    // containing it is a group whose contents were not what was described, and
    // finding that out before the prompt is the whole point.
    const problems = sweep.closeOutProblems([WRONG_SENDER], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toContain("transaction 1 is not sent by you");
  });

  test("a transfer paying somebody else", () => {
    const problems = sweep.closeOutProblems([TO_STRANGER], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toContain("transaction 1 pays somebody else");
  });

  test("a transfer that closes nothing", () => {
    const problems = sweep.closeOutProblems([NO_CLOSE], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toContain("transaction 1 does not close the holding");
  });

  test("a well-formed close-out of an asset the plan never listed", () => {
    // The rule that makes this bind rather than restate the response. Nothing
    // is wrong with this transaction in isolation - it is a correct close-out
    // to the right owner. It is simply not the one that was described.
    const problems = sweep.closeOutProblems([WRONG_ASSET], ADDRESS, [
      EMPTY_HOLDING,
    ]);
    expect(problems).toEqual([
      "transaction 1 closes asset 999, which was not listed",
    ]);
  });

  test("the right asset closed to the wrong address", () => {
    // Asset 5 was described as an empty holding, so it must close to self.
    // Here it closes to the creator, which for a *held* asset would be a
    // forfeit - a real transfer of value the plan did not describe.
    const problems = sweep.closeOutProblems(
      [FORFEIT_TO_CREATOR],
      ADDRESS,
      [{ asset: 9, amount: "0", creator: CREATOR }]
    );
    expect(problems).toEqual([
      "transaction 1 closes asset 9 to an unexpected address",
    ]);
  });

  test("one bad transaction among fifteen good ones", () => {
    // The reason a whitelist exists at all: nobody reads the sixteenth line.
    const group = new Array(15).fill(CLOSE_TO_SELF).concat([PAYMENT_DRAIN]);
    const problems = sweep.closeOutProblems(group, ADDRESS, [EMPTY_HOLDING]);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toMatch(/transaction 16 is a pay/);
  });

  test("a group over the protocol limit", () => {
    const group = new Array(17).fill(CLOSE_TO_SELF);
    const problems = sweep.closeOutProblems(group, ADDRESS, [EMPTY_HOLDING]);
    expect(problems[0]).toMatch(/over the limit of 16/);
  });

  test("a transaction that will not decode", () => {
    const problems = sweep.closeOutProblems(["!!!!"], ADDRESS, [EMPTY_HOLDING]);
    expect(problems).toEqual(["transaction 1 could not be decoded"]);
  });

  test("an empty or absent group", () => {
    expect(sweep.closeOutProblems([], ADDRESS, [])).toEqual([
      "the group carries no transactions",
    ]);
    expect(sweep.closeOutProblems(null, ADDRESS, [])).toEqual([
      "the group carries no transactions",
    ]);
  });

  test("an unreadable sweep address, before anything else is judged", () => {
    expect(sweep.closeOutProblems([CLOSE_TO_SELF], "nope", [])).toEqual([
      "the address being swept is unreadable",
    ]);
  });

  test("a described holding with no creator cannot match a forfeit", () => {
    const problems = sweep.closeOutProblems(
      [FORFEIT_TO_CREATOR],
      ADDRESS,
      [{ asset: 9, amount: "1000", creator: null }]
    );
    expect(problems).toEqual([
      "transaction 1 closes asset 9 to an unexpected address",
    ]);
  });

  test("a missing holdings list refuses everything rather than allowing it", () => {
    const problems = sweep.closeOutProblems([CLOSE_TO_SELF], ADDRESS, undefined);
    expect(problems).toEqual([
      "transaction 1 closes asset 5, which was not listed",
    ]);
  });
});

describe("closeOutProblems bounds the fee", () => {
  // `S3`: nothing else does. The engine builds these from the node's suggested
  // parameters, the bridge preserves whatever arrives, and mainnet will take a
  // fee up to the account's entire spendable balance.
  test("a five ALGO fee is refused", () => {
    const problems = sweep.closeOutProblems(
      [FAT_FEE],
      ADDRESS,
      [FORFEITED_HOLDING]
    );
    expect(problems).toContain(
      "transaction 1 pays a fee of 5.00 ALGO, over the limit of 0.01"
    );
  });

  test("a fee exactly at the limit is allowed", () => {
    // Congestion legitimately raises what a transaction costs, so the bound
    // cannot sit at the protocol minimum.
    expect(
      sweep.closeOutProblems([AT_FEE_LIMIT], ADDRESS, [FORFEITED_HOLDING])
    ).toEqual([]);
  });

  test("one microALGO over the limit is refused", () => {
    expect(
      sweep.closeOutProblems([OVER_FEE_LIMIT], ADDRESS, [FORFEITED_HOLDING])
    ).toHaveLength(1);
  });

  test("the limit is a fraction of what a close-out returns", () => {
    // Not decoration. Because the cap is a tenth of the minimum balance, a
    // group of any size pays at most a tenth of what it releases - so "the
    // fees exceed what the group recovers" is unreachable and needs no rule of
    // its own. This test is what fails if someone raises the constant past the
    // point where that stops being true.
    expect(sweep.MAX_CLOSE_OUT_FEE).toBeLessThan(sweep.HOLDING_MINIMUM_BALANCE);
    expect(sweep.MAX_CLOSE_OUT_FEE * sweep.CLOSE_OUTS_PER_GROUP).toBeLessThan(
      sweep.HOLDING_MINIMUM_BALANCE * sweep.CLOSE_OUTS_PER_GROUP
    );
  });

  test("a transaction with no fee field at all is allowed", () => {
    // Canonical encoding omits a zero fee entirely, so the rule reads an
    // absent field. Refusing that would refuse a group that costs nothing.
    expect(sweep.decodeMsgpack(sweep.b64ToBytes(ZERO_FEE)).fee).toBeUndefined();
    expect(sweep.closeOutProblems([ZERO_FEE], ADDRESS, [EMPTY_HOLDING])).toEqual(
      []
    );
  });

  test("a mid-sized fee is still refused well below what a close returns", () => {
    // 0.05 ALGO is half of what closing the holding hands back, and a reader
    // told they recover 0.1 would be surprised to net 0.05.
    const problems = sweep.closeOutProblems(
      [HALF_MBR_FEE],
      ADDRESS,
      [EMPTY_HOLDING]
    );
    expect(problems).toEqual([
      "transaction 1 pays a fee of 0.05 ALGO, over the limit of 0.01",
    ]);
  });

  test("an honest group passes both fee rules", () => {
    expect(
      sweep.closeOutProblems(
        [CLOSE_TO_SELF, FORFEIT_TO_CREATOR],
        ADDRESS,
        [EMPTY_HOLDING, FORFEITED_HOLDING]
      )
    ).toEqual([]);
  });
});

describe("forfeitTargetProblems", () => {
  /**
   * `S2`: `closeOutProblems` compares a forfeit's destination against
   * `described[].creator`, and both halves arrive in the same response. These
   * cover the half that does not - the creator read from the chain.
   */
  const bridgeSaying = (creator) => ({
    assetCreator: jest.fn().mockResolvedValue(creator),
  });

  test("a forfeit to the chain's creator is accepted", async () => {
    const bridge = bridgeSaying(CREATOR);
    await expect(
      sweep.forfeitTargetProblems([FORFEIT_TO_CREATOR], [FORFEITED_HOLDING], bridge)
    ).resolves.toEqual([]);
    expect(bridge.assetCreator).toHaveBeenCalledWith(9);
  });

  test("a forfeit the engine described consistently is still refused", async () => {
    // The finding itself. `closeOutProblems` passes this group, because the
    // plan names the same address the transaction closes to; the chain does
    // not agree, and that is the only opinion here not supplied by the engine.
    const described = [{ asset: 9, amount: "1000", creator: ADDRESS }];
    expect(
      sweep.closeOutProblems([FORFEIT_TO_CREATOR], ADDRESS, described)
    ).not.toEqual([]);

    await expect(
      sweep.forfeitTargetProblems(
        [FORFEIT_TO_CREATOR],
        [FORFEITED_HOLDING],
        bridgeSaying(ADDRESS)
      )
    ).resolves.toEqual([
      "transaction 1 forfeits asset 9 to an address that is not its creator on chain",
    ]);
  });

  test("an empty holding needs no lookup at all", async () => {
    // Its destination is the connected account, which was never in doubt.
    const bridge = bridgeSaying(CREATOR);
    await expect(
      sweep.forfeitTargetProblems([CLOSE_TO_SELF], [EMPTY_HOLDING], bridge)
    ).resolves.toEqual([]);
    expect(bridge.assetCreator).not.toHaveBeenCalled();
  });

  test("a bridge that cannot answer refuses rather than allows", async () => {
    // Fails closed: refusing costs a reader one sweep, signing an unverifiable
    // forfeit costs them the holding.
    await expect(
      sweep.forfeitTargetProblems([FORFEIT_TO_CREATOR], [FORFEITED_HOLDING], {})
    ).resolves.toEqual([
      "this wallet connection cannot confirm who an asset's creator is, and " +
        "the sweep will not give a holding away on the engine's word alone",
    ]);
  });

  test("an unreadable asset refuses rather than allows", async () => {
    await expect(
      sweep.forfeitTargetProblems(
        [FORFEIT_TO_CREATOR],
        [FORFEITED_HOLDING],
        bridgeSaying(null)
      )
    ).resolves.toEqual([
      "transaction 1 forfeits asset 9, whose creator could not be confirmed on chain",
    ]);
  });

  test("a lookup that throws is a refusal, not an exception", async () => {
    const bridge = {
      assetCreator: jest.fn().mockRejectedValue(new Error("network down")),
    };
    await expect(
      sweep.forfeitTargetProblems([FORFEIT_TO_CREATOR], [FORFEITED_HOLDING], bridge)
    ).resolves.toHaveLength(1);
  });

  test("one lookup per distinct asset, however many transactions", async () => {
    const bridge = bridgeSaying(CREATOR);
    await sweep.forfeitTargetProblems(
      [FORFEIT_TO_CREATOR, FORFEIT_TO_CREATOR, FORFEIT_TO_CREATOR],
      [FORFEITED_HOLDING],
      bridge
    );
    expect(bridge.assetCreator).toHaveBeenCalledTimes(1);
  });

  test("a missing holdings list forfeits nothing, so it asks nothing", async () => {
    const bridge = { assetCreator: jest.fn() };
    await expect(
      sweep.forfeitTargetProblems([FORFEIT_TO_CREATOR], undefined, bridge)
    ).resolves.toEqual([]);
    expect(bridge.assetCreator).not.toHaveBeenCalled();
  });

  test("an undecodable transaction is left to closeOutProblems", async () => {
    await expect(
      sweep.forfeitTargetProblems(["!!!"], [FORFEITED_HOLDING], bridgeSaying(CREATOR))
    ).resolves.toEqual([]);
  });
});

describe("signAction", () => {
  test("a close-out group is inspected before it reaches the wallet", async () => {
    const bridge = { signAndSend: jest.fn(), signAndSendPartial: jest.fn() };
    const action = {
      kind: "close",
      transactions: [PAYMENT_DRAIN],
      holdings: [EMPTY_HOLDING],
    };
    await expect(signActionOf(action, bridge)).rejects.toThrow(
      /This group was refused/
    );
    expect(bridge.signAndSend).not.toHaveBeenCalled();
  });

  test("a good close-out group is signed", async () => {
    const bridge = { signAndSend: jest.fn().mockResolvedValue("TXID") };
    const action = {
      kind: "close",
      transactions: [CLOSE_TO_SELF],
      holdings: [EMPTY_HOLDING],
    };
    await expect(signActionOf(action, bridge)).resolves.toBe("TXID");
    expect(bridge.signAndSend).toHaveBeenCalledWith(
      [sweep.b64ToBytes(CLOSE_TO_SELF)],
      {}
    );
  });

  test("the wallet is handed bytes, never the base64 it arrived as", async () => {
    // The bug this is holding shut, in the words the reader got:
    //
    //     RangeError: Extra 339 of 340 byte(s) found at buffer[1]
    //
    // `signAndSend` takes `Uint8Array[]` and passes each entry to algosdk's
    // `decodeUnsignedTransaction`, which turns an array-like of characters
    // into one byte each. A close-out is exactly 340 base64 characters, so
    // the decoder read a complete msgpack object in the first byte and called
    // the remaining 339 trailing garbage - naming neither base64 nor this
    // widget. Asserted on the *type* because the length and the content were
    // both plausible; only the type was wrong.
    const bridge = {
      signAndSend: jest.fn().mockResolvedValue("TXID"),
      assetCreator: jest.fn().mockResolvedValue(CREATOR),
    };
    const action = {
      kind: "close",
      transactions: [CLOSE_TO_SELF, FORFEIT_TO_CREATOR],
      holdings: [EMPTY_HOLDING, FORFEITED_HOLDING],
    };
    await signActionOf(action, bridge);

    const [group] = bridge.signAndSend.mock.calls[0];
    expect(group).toHaveLength(2);
    group.forEach((entry, index) => {
      expect(entry).toBeInstanceOf(Uint8Array);
      // Base64 is a third longer than what it encodes, so a group that was
      // never decoded is exactly as long as the strings that arrived - which
      // is the arithmetic behind "340 byte(s)" in the reader's error.
      expect(entry.length).toBeLessThan(action.transactions[index].length);
    });
  });

  test("a conversion goes through the quote-signed path", async () => {
    // It carries the engine's quote authorisation, which `signAndSend` would
    // destroy by re-assigning group ids.
    const bridge = { signAndSendPartial: jest.fn().mockResolvedValue("TXID") };
    const action = {
      kind: "convert",
      transactions: [CLOSE_TO_SELF],
      signed_transactions: { 0: FORFEIT_TO_CREATOR },
      quote_signer_index: 0,
    };
    await expect(signActionOf(action, bridge)).resolves.toBe("TXID");
    expect(bridge.signAndSendPartial).toHaveBeenCalledWith({
      transactions: [sweep.b64ToBytes(CLOSE_TO_SELF)],
      signedTransactions: { 0: sweep.b64ToBytes(FORFEIT_TO_CREATOR) },
      quoteSignerIndex: 0,
    });
  });

  test("a wallet without the quote-signed path is told so", async () => {
    const bridge = { signAndSend: jest.fn() };
    const action = { kind: "convert", transactions: ["X"] };
    await expect(signActionOf(action, bridge)).rejects.toThrow(
      /does not support quote-signed groups/
    );
  });

  function signActionOf(action, bridge) {
    return sweep.signAction(action, ADDRESS, bridge);
  }
});

describe("partialGroup", () => {
  test("a direct group carries no backend signature and still converts", () => {
    // `quote_signer_index` is only present on a routed group. The bridge
    // rejects the result either way, and it must reject it for what it is
    // rather than crash on a missing key on the way there.
    const group = sweep.partialGroup({ transactions: [CLOSE_TO_SELF] });
    expect(group.signedTransactions).toEqual({});
    expect(group.quoteSignerIndex).toBeNaN();
  });

  test("an action with no transactions produces an empty group", () => {
    expect(sweep.partialGroup({})).toEqual({
      transactions: [],
      signedTransactions: {},
      quoteSignerIndex: NaN,
    });
  });
});

describe("fetchPlan", () => {
  afterEach(() => {
    delete global.fetch;
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  test("posts to the gated address and returns the plan", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ next: null }),
    });
    const plan = await sweep.fetchPlan("/dustsweep/plan", ADDRESS, {
      threshold_algo: 1,
    });
    expect(plan).toEqual({ next: null });
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/dustsweep/plan?address=" + ADDRESS);
    expect(JSON.parse(options.body)).toEqual({ threshold_algo: 1 });
  });

  test("sends the CSRF token Django set", () => {
    document.cookie = "csrftoken=abc123";
    expect(sweep.csrfToken()).toBe("abc123");
  });

  test("reports no token rather than sending undefined", () => {
    expect(sweep.csrfToken()).toBe("");
  });

  test("raises the engine's own sentence on a refusal", async () => {
    // A restricted router answers 503 explaining why. That sentence is the
    // only thing a reader could act on, so it must survive to the panel.
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: "RESTRICT_TO_ADMIN, so no group" }),
    });
    await expect(sweep.fetchPlan("/p", ADDRESS, {})).rejects.toThrow(
      "RESTRICT_TO_ADMIN, so no group"
    );
  });

  test("falls back to a readable message when there is no body", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, json: async () => ({}) });
    await expect(sweep.fetchPlan("/p", ADDRESS, {})).rejects.toThrow(
      "the sweep is unavailable"
    );
  });

  test("defaults the options to an empty body", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    await sweep.fetchPlan("/p", ADDRESS);
    expect(global.fetch.mock.calls[0][1].body).toBe("{}");
  });
});

describe("summarise", () => {
  test("counts the signatures and the certain half of the recovery", () => {
    expect(
      sweep.summarise({
        summary: { prompts: 7, recoverable: 3_000_000 },
        next: { kind: "close" },
      })
    ).toBe("7 signatures to recover about 3.00 ALGO");
  });

  test("says signature, singular, when there is one", () => {
    expect(
      sweep.summarise({
        summary: { prompts: 1, recoverable: 100_000 },
        next: { kind: "close" },
      })
    ).toBe("1 signature to recover about 0.10 ALGO");
  });

  test("says nothing to sweep when there is nothing to do", () => {
    expect(sweep.summarise({ summary: {}, next: null })).toBe(
      "Nothing to sweep."
    );
  });

  test("survives a plan with no summary at all", () => {
    // An engine answering something unexpected must not blank the panel with
    // a TypeError - the user still needs to be told nothing happened.
    expect(sweep.summarise({})).toBe("Nothing to sweep.");
  });

  test("reports zero when nothing is recoverable", () => {
    expect(
      sweep.summarise({ summary: { prompts: 1 }, next: { kind: "convert" } })
    ).toBe("1 signature to recover about 0.00 ALGO");
  });

  test("mentions holdings it refused to value", () => {
    // These are the ones a user might otherwise think were missed. Saying so
    // is what makes the refusal to guess visible rather than silent.
    expect(sweep.summarise({ summary: { unpriced: 3 }, next: null })).toBe(
      "Nothing to sweep. 3 holdings could not be valued and were left alone."
    );
  });
});

describe("whenSweepReady", () => {
  afterEach(() => {
    delete window.asastatsSwap;
  });

  test("runs at once when the bridge is already published", () => {
    window.asastatsSwap = {};
    const fn = jest.fn();
    sweep.whenSweepReady(fn);
    expect(fn).toHaveBeenCalled();
  });

  test("waits for the bridge's ready event otherwise", () => {
    const fn = jest.fn();
    sweep.whenSweepReady(fn);
    expect(fn).not.toHaveBeenCalled();
    window.dispatchEvent(new CustomEvent("asastats:swap-ready"));
    expect(fn).toHaveBeenCalled();
  });
});

/* ------------------------------------------------------------------ *
 * the per-line choice, which is what makes the list a choice
 * ------------------------------------------------------------------ */

const line = (asset, disposition, extra = {}) => ({
  asset,
  unit: "U" + asset,
  amount: "1",
  value: 1,
  creator: CREATOR,
  disposition,
  reason: "because",
  ...extra,
});

describe("isActionable", () => {
  test.each(["close", "forfeit", "convert", "unpriced"])(
    "%s is something a sweep can act on",
    (disposition) => {
      expect(sweep.isActionable(line(1, disposition))).toBe(true);
    }
  );

  test("keep is not, so it carries no control at all", () => {
    // Not a disabled checkbox - no checkbox. A control that cannot be used is
    // an invitation to try.
    expect(sweep.isActionable(line(1, "keep"))).toBe(false);
  });

  test("an unknown disposition is treated as not actionable", () => {
    // Fails closed: a disposition this build has never heard of must not
    // become a line the reader can sweep.
    expect(sweep.isActionable(line(1, "something-new"))).toBe(false);
  });

  test("committed is not, so nothing the reader does can sweep it", () => {
    // The whole point of the disposition. These are the tokens an account
    // holds because of a position in some dApp, and the engine refuses them
    // whatever the request body says - so offering a control here would be a
    // control that silently does nothing.
    expect(sweep.isActionable(line(1, "committed"))).toBe(false);
    expect(sweep.includedByDefault(line(1, "committed"))).toBe(false);
  });

  test("committed reaches neither list the reader's choices produce", () => {
    const choices = new Map([[1, true]]);
    expect(sweep.choicePayload([line(1, "committed")], choices)).toEqual({
      opted_in: [],
      excluded: [],
    });
  });
});

describe("badgeFor", () => {
  test.each([
    ["close", "Close", "close"],
    ["forfeit", "Forfeit", "forfeit"],
    ["convert", "Convert", "convert"],
    ["unpriced", "Unpriced", "unpriced"],
  ])("%s keeps its own badge", (disposition, label, tone) => {
    expect(sweep.badgeFor(line(1, disposition))).toEqual(
      expect.objectContaining({ label, tone })
    );
  });

  test("committed reads as In use rather than as a verdict on its value", () => {
    // "Committed" is the engine's word for it; the reader's question is why
    // their token is not being swept, and the answer is that it is in use
    // somewhere. The sentence in `reason` says where.
    expect(sweep.badgeFor(line(1, "committed"))).toEqual({
      label: "In use",
      tone: "committed",
    });
  });

  test("keep still reads as Keep", () => {
    expect(sweep.badgeFor(line(1, "keep"))).toEqual({
      label: "Keep",
      tone: "keep",
    });
  });

  test("a disposition this build has never heard of falls back to Keep", () => {
    // The safe fallback: an unrecognised line is shown as left alone, which is
    // also what `isActionable` will do with it.
    expect(sweep.badgeFor(line(1, "something-new"))).toEqual({
      label: "Keep",
      tone: "keep",
    });
  });
});

describe("assetLabels", () => {
  test("carries the asset id alongside the unit", () => {
    // The unit alone cannot be checked against anything: unit names are not
    // unique on Algorand, so a reader about to close out "USDC" has no way to
    // tell which "USDC" it is without the id.
    expect(sweep.assetLabels(line(31566704, "close"))).toEqual({
      unit: "U31566704",
      id: "#31566704",
    });
  });

  test("an asset whose unit could not be read still names itself", () => {
    // `_asset_facts` returns no unit for an asset whose parameters are
    // unreadable, and those are exactly the rows worth looking up.
    expect(sweep.assetLabels(line(5, "unpriced", { unit: null }))).toEqual({
      unit: "Unnamed",
      id: "#5",
    });
  });

  test("asset 0 is still shown as 0 rather than as unknown", () => {
    // Falsy but real. ALGO never reaches a row, but an id must never be able to
    // read as missing because of its value.
    expect(sweep.assetLabels(line(0, "keep")).id).toBe("#0");
  });

  test("a line with no asset at all says so instead of inventing one", () => {
    expect(sweep.assetLabels({}).id).toBe("#?");
    expect(sweep.assetLabels(undefined)).toEqual({ unit: "Unnamed", id: "#?" });
  });
});

describe("degradedNotice", () => {
  test("says nothing about a plan that is whole", () => {
    expect(sweep.degradedNotice({})).toBe("");
    expect(sweep.degradedNotice(null)).toBe("");
    expect(
      sweep.degradedNotice({
        evaluation_unavailable: null,
        conversions_unavailable: null,
      })
    ).toBe("");
  });

  test("an unreadable evaluation is explained as a limit on the sweep", () => {
    // Not on the account. A reader who sees three of their thirty holdings
    // offered will otherwise conclude the other twenty-seven are gone.
    const notice = sweep.degradedNotice({ evaluation_unavailable: "no redis" });
    expect(notice).toContain("only empty holdings are offered");
    expect(notice).toContain("no redis");
  });

  test("a router outage is explained as losing the conversions only", () => {
    const notice = sweep.degradedNotice({ conversions_unavailable: "no app" });
    expect(notice).toContain("Conversions are unavailable");
    expect(notice).toContain("no app");
  });

  test("the evaluation outage is the one reported when both are true", () => {
    // It is the larger of the two and subsumes the other: without an
    // evaluation there is nothing to convert anyway, so naming the router
    // would explain the wrong half of a plan that looks empty.
    const notice = sweep.degradedNotice({
      evaluation_unavailable: "no redis",
      conversions_unavailable: "no app",
    });
    expect(notice).toContain("only empty holdings are offered");
    expect(notice).not.toContain("no app");
  });
});

describe("includedByDefault", () => {
  test.each(["close", "forfeit", "convert"])(
    "%s is swept unless the reader says otherwise",
    (disposition) => {
      expect(sweep.includedByDefault(line(1, disposition))).toBe(true);
    }
  );

  test("unpriced starts off, because the engine is admitting it does not know", () => {
    // The asymmetry that keeps the forfeit safe. Everything the engine could
    // value is on by default; the one disposition where it could not is the
    // one the reader has to switch on themselves.
    expect(sweep.includedByDefault(line(1, "unpriced"))).toBe(false);
  });

  test("keep is off, whatever else happens", () => {
    expect(sweep.includedByDefault(line(1, "keep"))).toBe(false);
  });
});

describe("choicePayload", () => {
  test("sends nothing when the reader has touched nothing", () => {
    // Only deviations cross the wire, which is what lets the plan be refetched
    // after every signature without resetting anyone's decisions.
    const holdings = [line(1, "close"), line(2, "forfeit"), line(3, "unpriced")];
    expect(sweep.choicePayload(holdings, new Map())).toEqual({
      opted_in: [],
      excluded: [],
    });
  });

  test("a deselected forfeit becomes an exclusion", () => {
    const holdings = [line(2, "forfeit")];
    expect(sweep.choicePayload(holdings, new Map([[2, false]]))).toEqual({
      opted_in: [],
      excluded: [2],
    });
  });

  test("a selected unpriced holding becomes an opt-in", () => {
    const holdings = [line(3, "unpriced")];
    expect(sweep.choicePayload(holdings, new Map([[3, true]]))).toEqual({
      opted_in: [3],
      excluded: [],
    });
  });

  test("selecting something already on adds nothing", () => {
    const holdings = [line(1, "close")];
    expect(sweep.choicePayload(holdings, new Map([[1, true]]))).toEqual({
      opted_in: [],
      excluded: [],
    });
  });

  test("deselecting something already off adds nothing", () => {
    // In particular it must NOT land in `excluded`: an unpriced holding is not
    // being swept anyway, and naming it would be noise the engine has to
    // reconcile against `opted_in`.
    const holdings = [line(3, "unpriced")];
    expect(sweep.choicePayload(holdings, new Map([[3, false]]))).toEqual({
      opted_in: [],
      excluded: [],
    });
  });

  test("a kept holding can never reach either list", () => {
    // The reader has no control on that line, but a stale choice from an
    // earlier plan could still be in the map - so this is the guard that stops
    // a reclassified holding being swept on yesterday's answer.
    const holdings = [line(9, "keep")];
    const choices = new Map([[9, true]]);
    expect(sweep.choicePayload(holdings, choices)).toEqual({
      opted_in: [],
      excluded: [],
    });
  });

  test("the two lists never name the same asset", () => {
    const holdings = [line(1, "close"), line(2, "forfeit"), line(3, "unpriced")];
    const choices = new Map([
      [1, false],
      [2, false],
      [3, true],
    ]);
    const payload = sweep.choicePayload(holdings, choices);
    expect(payload).toEqual({ opted_in: [3], excluded: [1, 2] });
    expect(payload.opted_in.filter((a) => payload.excluded.includes(a))).toEqual(
      []
    );
  });

  test("survives no holdings and no choices", () => {
    expect(sweep.choicePayload(undefined, undefined)).toEqual({
      opted_in: [],
      excluded: [],
    });
  });
});

describe("isIncluded", () => {
  test("an explicit choice wins over the default", () => {
    expect(sweep.isIncluded(line(1, "close"), new Map([[1, false]]))).toBe(false);
    expect(sweep.isIncluded(line(3, "unpriced"), new Map([[3, true]]))).toBe(true);
  });

  test("falls back to the default without a choice", () => {
    expect(sweep.isIncluded(line(1, "close"), new Map())).toBe(true);
    expect(sweep.isIncluded(line(3, "unpriced"), new Map())).toBe(false);
  });

  test("survives a missing choices map", () => {
    expect(sweep.isIncluded(line(1, "close"), null)).toBe(true);
  });
});

describe("visibleLines", () => {
  const holdings = [
    line(1, "close"),
    line(9, "keep"),
    line(3, "unpriced"),
    line(4, "committed"),
  ];

  test("the default view shows only what the sweep would act on", () => {
    expect(sweep.visibleLines(holdings, "sweeping").map((h) => h.asset)).toEqual([
      1, 3,
    ]);
  });

  test("the other view shows everything, including what was left alone", () => {
    // A reader who cannot see why their token was skipped has no way to tell
    // "kept deliberately" from "missed" - and after this change the commonest
    // reason for skipping is that the token is somebody's dApp position, which
    // is exactly the thing they will come looking for.
    expect(sweep.visibleLines(holdings, "all")).toHaveLength(4);
    expect(sweep.visibleLines(holdings, "all").map((h) => h.disposition)).toContain(
      "committed"
    );
  });

  test("does not hand back the caller's own array to mutate", () => {
    expect(sweep.visibleLines(holdings, "all")).not.toBe(holdings);
  });

  test("survives no holdings", () => {
    expect(sweep.visibleLines(undefined, "all")).toEqual([]);
    expect(sweep.visibleLines(undefined, "sweeping")).toEqual([]);
  });
});

describe("summaryFigures", () => {
  test("the four questions a reader actually has", () => {
    // `Network fees` joined these for `S3`: the planner had always computed it
    // and sent it, and nothing rendered it, so no number on this screen would
    // have moved if every fee in the group had been a thousand times larger.
    const figures = sweep.summaryFigures({
      summary: {
        recoverable: 3_000_000,
        fees: 16_000,
        prompts: 7,
        close: 10,
        forfeit: 15,
        convert: 5,
      },
    });
    expect(figures).toEqual([
      { label: "You recover", value: "3.00 ALGO" },
      { label: "Network fees", value: "0.02 ALGO" },
      { label: "Signatures", value: "7" },
      { label: "Holdings", value: "30" },
    ]);
  });

  test("counts only what will be swept, not what is kept", () => {
    const figures = sweep.summaryFigures({
      summary: { close: 1, keep: 99, unpriced: 4 },
    });
    expect(figures[3].value).toBe("1");
  });

  test("survives an empty plan", () => {
    expect(sweep.summaryFigures({})).toEqual([
      { label: "You recover", value: "0.00 ALGO" },
      { label: "Network fees", value: "0.00 ALGO" },
      { label: "Signatures", value: "0" },
      { label: "Holdings", value: "0" },
    ]);
  });
});

describe("ctaLabel", () => {
  test("capitalises the engine's own sentence", () => {
    expect(sweep.ctaLabel({ next: { label: "close 16 holdings" } })).toBe(
      "Close 16 holdings"
    );
  });

  test("says so when there is nothing to do", () => {
    expect(sweep.ctaLabel({ next: null })).toBe("Nothing to sweep");
    expect(sweep.ctaLabel(null)).toBe("Nothing to sweep");
  });

  test("falls back rather than rendering an empty button", () => {
    expect(sweep.ctaLabel({ next: { label: "" } })).toBe("Sign the next group");
  });
});

describe("progressLabel", () => {
  test("counts signatures, which is the unit the reader spends", () => {
    expect(sweep.progressLabel({ summary: { prompts: 7 } }, 0)).toBe(
      "Signature 1 of 7"
    );
    expect(sweep.progressLabel({ summary: { prompts: 6 } }, 1)).toBe(
      "Signature 2 of 7"
    );
  });

  test("is empty before anything is planned", () => {
    expect(sweep.progressLabel({ summary: {} }, 0)).toBe("");
    expect(sweep.progressLabel(null, 0)).toBe("");
  });

  test("still shows the total after the last signature", () => {
    // prompts drops to 0 when the sweep finishes; the reader should see that
    // they signed four of four, not a blank.
    expect(sweep.progressLabel({ summary: { prompts: 0 } }, 4)).toBe(
      "Signature 5 of 4"
    );
  });
});

describe("algo", () => {
  test.each([
    [100_000, "0.10"],
    [3_000_000, "3.00"],
    [0, "0.00"],
    [null, "0.00"],
    [undefined, "0.00"],
  ])("%p microALGO reads as %s", (given, expected) => {
    expect(sweep.algo(given)).toBe(expected);
  });
});

/* ------------------------------------------------------------------ *
 * which account the address-page entry may offer
 * ------------------------------------------------------------------ */

describe("sweepableAddress", () => {
  const OTHER = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU";

  test("offers the connected account when the page shows it", () => {
    expect(sweep.sweepableAddress([ADDRESS, OTHER], ADDRESS)).toBe(ADDRESS);
  });

  test("offers nothing while no wallet is connected", () => {
    // The reason the button is rendered hidden rather than pointed at a guess:
    // a sweep built for an account the wallet is not on cannot be signed, and
    // the reader would find that out at the signature prompt.
    expect(sweep.sweepableAddress([ADDRESS, OTHER], null)).toBe("");
    expect(sweep.sweepableAddress([ADDRESS, OTHER], "")).toBe("");
  });

  test("offers nothing when the connected account is not on this page", () => {
    // A wallet is connected to one account at a time and the reader may be
    // looking at somebody else's address. The sweep acts on what is on screen.
    expect(sweep.sweepableAddress([OTHER], ADDRESS)).toBe("");
  });

  test("offers nothing when the reader owns none of the page's addresses", () => {
    expect(sweep.sweepableAddress([], ADDRESS)).toBe("");
    expect(sweep.sweepableAddress(null, ADDRESS)).toBe("");
  });

  test("never settles for a partial match", () => {
    // Addresses are compared whole. A prefix match would let a lookalike
    // address stand in for the one the wallet actually holds.
    expect(sweep.sweepableAddress([ADDRESS], ADDRESS.slice(0, 40))).toBe("");
    expect(sweep.sweepableAddress([ADDRESS.slice(0, 40)], ADDRESS)).toBe("");
  });
});

describe("shortAddress", () => {
  test("keeps both ends, which is what tells two addresses apart", () => {
    expect(sweep.shortAddress(ADDRESS)).toBe(
      ADDRESS.slice(0, 6) + "…" + ADDRESS.slice(-4)
    );
  });

  test("has nothing to say about nothing", () => {
    expect(sweep.shortAddress("")).toBe("");
    expect(sweep.shortAddress(null)).toBe("");
  });
});
