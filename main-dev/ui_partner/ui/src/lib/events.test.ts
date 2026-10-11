// FROZEN: written by the lead. Do not edit; report if a case looks wrong.
import { describe, expect, it } from "vitest";
import { needed } from "./events";

describe("80% rounded up", () => {
  it("needs 3, 4, 4, 5, 6 of 3 to 7 seats", () => {
    expect([3, 4, 5, 6, 7].map(needed)).toEqual([3, 4, 4, 5, 6]);
  });
});
