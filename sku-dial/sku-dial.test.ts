/**
 * Pure digit/auto-dash state behind the SKU dialer's numeric mode
 * (lib/search/sku-dial.ts; plan: tasks/sku-dialer-search.md §4 "Input").
 * The invariant under test: the dash is DERIVED after the 2-digit prefix,
 * never typed, never independently deleted.
 */
import { describe, it, expect } from "vitest";
import {
  SKU_DIAL_MAX_DIGITS,
  appendDialDigit,
  deleteDialDigit,
  formatDialTerm,
} from "./sku-dial";

describe("appendDialDigit", () => {
  it("appends digits 0-9 and ignores everything else", () => {
    expect(appendDialDigit("5", "5")).toBe("55");
    expect(appendDialDigit("55", "0")).toBe("550");
    // The operator can't type a dash — it's derived, not input.
    expect(appendDialDigit("55", "-")).toBe("55");
    expect(appendDialDigit("55", "a")).toBe("55");
    expect(appendDialDigit("55", "Enter")).toBe("55");
    expect(appendDialDigit("55", "12")).toBe("55");
  });

  it("caps at SKU_DIAL_MAX_DIGITS — a full canonical SKU fits exactly", () => {
    // "5500000012" (10 digits) formats to canonical 55-00000012.
    const full = "5500000012";
    expect(full).toHaveLength(SKU_DIAL_MAX_DIGITS);
    expect(appendDialDigit(full, "9")).toBe(full);
  });
});

describe("deleteDialDigit", () => {
  it("removes the last digit; the derived dash goes with it", () => {
    // Display "55-" (digits "55") → backspace → "5". One press, not two —
    // the operator never deletes the dash itself.
    expect(deleteDialDigit("55")).toBe("5");
    expect(deleteDialDigit("5512")).toBe("551");
    expect(deleteDialDigit("5")).toBe("");
    expect(deleteDialDigit("")).toBe("");
  });
});

describe("formatDialTerm", () => {
  it("inserts the dash the instant the 2nd digit lands (359/359 prod prefixes are 2-digit)", () => {
    expect(formatDialTerm("")).toBe("");
    expect(formatDialTerm("5")).toBe("5");
    expect(formatDialTerm("55")).toBe("55-");
    expect(formatDialTerm("551")).toBe("55-1");
    expect(formatDialTerm("5512")).toBe("55-12");
  });

  it("a fully-dialed canonical SKU formats to the exact zero-padded form", () => {
    expect(formatDialTerm("5500000012")).toBe("55-00000012");
  });

  it("round-trips with append/delete — display state never desyncs", () => {
    let digits = "";
    for (const k of ["5", "5", "1", "2"]) digits = appendDialDigit(digits, k);
    expect(formatDialTerm(digits)).toBe("55-12");
    digits = deleteDialDigit(deleteDialDigit(digits));
    expect(formatDialTerm(digits)).toBe("55-");
    digits = deleteDialDigit(digits);
    expect(formatDialTerm(digits)).toBe("5");
  });
});
