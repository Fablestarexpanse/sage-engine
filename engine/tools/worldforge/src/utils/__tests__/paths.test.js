import { describe, expect, it } from "vitest";
import { joinPaths } from "../paths.js";

describe("joinPaths", () => {
  it("uses the root's separator style", () => {
    expect(joinPaths("C:\\proj\\content", "world", "zones")).toBe("C:\\proj\\content\\world\\zones");
    expect(joinPaths("/proj/content", "world", "zones")).toBe("/proj/content/world/zones");
  });

  it("strips leading separators of segments and skips empty ones", () => {
    expect(joinPaths("/root/", "/a", "", null, "b.yaml")).toBe("/root/a/b.yaml");
  });

  it("falls back to '/' join when root is empty", () => {
    expect(joinPaths("", "a", "b")).toBe("a/b");
  });
});
