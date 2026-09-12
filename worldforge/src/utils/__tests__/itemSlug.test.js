import { describe, expect, it } from "vitest";
import { nextAvailableItemId, slugifyItemId } from "../itemSlug.js";

describe("slugifyItemId", () => {
  it("normalizes display names to safe ids", () => {
    expect(slugifyItemId("Rusty Sword!")).toBe("rusty_sword");
    expect(slugifyItemId("  D'argent  Blade ")).toBe("dargent_blade");
  });

  it("prefixes ids that don't start with a letter", () => {
    expect(slugifyItemId("9mm pistol")).toBe("i_9mm_pistol");
  });

  it("falls back to 'item' for empty input", () => {
    expect(slugifyItemId("")).toBe("item");
    expect(slugifyItemId("!!!")).toBe("item");
  });
});

describe("nextAvailableItemId", () => {
  it("returns the base when free and suffixes when taken", () => {
    expect(nextAvailableItemId([], "Sword")).toBe("sword");
    const taken = nextAvailableItemId(["sword"], "Sword");
    expect(taken).not.toBe("sword");
    expect(taken.startsWith("sword")).toBe(true);
  });
});
