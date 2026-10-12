import { describe, expect, it } from "vitest";

import { isEnabled } from "./feature-flags";

describe("isEnabled", () => {
  it("enables only an explicit true value", () => {
    expect(isEnabled("true")).toBe(true);
    expect(isEnabled("false")).toBe(false);
    expect(isEnabled(undefined)).toBe(false);
  });
});
