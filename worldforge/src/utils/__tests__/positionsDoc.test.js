import { describe, expect, it } from "vitest";
import { parsePositionsDoc, serializePositionsDoc } from "../positionsDoc.js";

describe("parsePositionsDoc", () => {
  it("returns an empty v2 doc for null/garbage input", () => {
    for (const raw of [null, undefined, 42, "x"]) {
      const doc = parsePositionsDoc(raw);
      expect(doc.version).toBe(2);
      expect(doc.positions).toEqual({});
      expect(doc.reference_image).toBeNull();
    }
  });

  it("round-trips a v2 doc including reference_image and floors", () => {
    const raw = {
      version: 2,
      positions: { a: { x: 1, y: 2 } },
      notes: [{ id: "n1", text: "hi" }],
      muted_edges: ["a|north|b"],
      floors: { a: 1 },
      reference_image: { path: "ref.png", opacity: 0.5 },
    };
    const doc = parsePositionsDoc(raw);
    expect(doc.positions.a).toEqual({ x: 1, y: 2 });
    expect(doc.floors).toEqual({ a: 1 });
    expect(doc.reference_image).toEqual({ path: "ref.png", opacity: 0.5 });
    const round = JSON.parse(serializePositionsDoc(doc));
    expect(round.reference_image).toEqual({ path: "ref.png", opacity: 0.5 });
    expect(round.muted_edges).toEqual(["a|north|b"]);
  });

  it("migrates legacy v1 inline positions and ignores non-position keys", () => {
    const doc = parsePositionsDoc({
      room_a: { x: 10, y: 20 },
      room_b: { x: 0, y: 0 },
      notes: "not-an-array-in-v1",
    });
    expect(doc.version).toBe(2);
    expect(Object.keys(doc.positions).sort()).toEqual(["room_a", "room_b"]);
    expect(doc.notes).toEqual([]);
  });

  it("serialize omits reference_image when absent", () => {
    const round = JSON.parse(serializePositionsDoc(parsePositionsDoc(null)));
    expect("reference_image" in round).toBe(false);
  });
});
