/** Unit tests for the pure helpers in folks.js (no DOM/wallet/SDK needed). */
const f = require("../../static/folks/folks.js");

describe("decimal <-> base units", () => {
  test("round-trips a fractional amount", () => {
    expect(f.decimalToBaseUnits("1.5", 6)).toBe(1500000n);
    expect(f.baseUnitsToDecimal(1500000n, 6)).toBe("1.5");
  });
  test("truncates excess decimal places", () => {
    expect(f.decimalToBaseUnits("0.0000001", 6)).toBe(0n);
  });
  test("formats whole amounts without a trailing dot", () => {
    expect(f.baseUnitsToDecimal(1000000n, 6)).toBe("1");
  });
});

describe("buildAssetOptions", () => {
  const holdings = [
    { id: 31566704, unit: "USDC", decimals: 6, amount: 5000000 },
    { id: 999, unit: "FOO", decimals: 2, amount: 0 }, // zero balance
    { id: 888, unit: "BAR", decimals: 3, amount: 10 },
  ];

  test("from = ALGO first, plus held assets with a positive balance", () => {
    const { from } = f.buildAssetOptions(holdings);
    expect(from[0]).toEqual({ id: 0, unit: "ALGO", decimals: 6 });
    const ids = from.map((a) => a.id);
    expect(ids).toContain(31566704);
    expect(ids).toContain(888);
    expect(ids).not.toContain(999); // zero balance excluded from 'from'
  });

  test("to = known targets unioned with held, de-duped by id", () => {
    const { to } = f.buildAssetOptions(holdings);
    const ids = to.map((a) => a.id);
    expect(ids).toContain(0); // ALGO (known)
    expect(ids).toContain(888); // BAR (held) usable as a target
    expect(ids.filter((x) => x === 31566704)).toHaveLength(1); // USDC once
  });
});

describe("unionById", () => {
  test("keeps the first occurrence of each id", () => {
    const out = f.unionById([{ id: 1, unit: "A" }], [{ id: 1, unit: "B" }, { id: 2 }]);
    expect(out).toEqual([{ id: 1, unit: "A" }, { id: 2 }]);
  });
});

describe("b64ToBytes", () => {
  test("decodes base64 to a Uint8Array", () => {
    expect(Array.from(f.b64ToBytes(btoa("ABC")))).toEqual([65, 66, 67]);
  });
});
