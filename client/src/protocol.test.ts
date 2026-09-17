import { describe, expect, it } from "vitest";

import { LOG_LIMIT, initialSession, parseFrame, reduce, socketUrl, type Session } from "./protocol";

const open = reduce(initialSession, { type: "open" });

function line(text: string | null, tick = 1) {
  return {
    type: "frame" as const,
    frame: { type: "line" as const, tick, key: "k", params: {}, text },
  };
}

describe("session reducer", () => {
  it("signs in and keeps what the world shows", () => {
    let s: Session = reduce(open, {
      type: "frame",
      frame: { type: "session", name: "Ada", character: 7 },
    });
    s = reduce(s, line("Hall\nBare stone."));
    s = reduce(s, line(null));
    s = reduce(s, { type: "sent", frame: { type: "command", text: "look" } });
    expect(s.signedIn).toEqual({ name: "Ada", character: 7 });
    expect(s.log.map((l) => [l.kind, l.text])).toEqual([
      ["world", "Hall\nBare stone."],
      ["echo", "> look"],
    ]);
  });

  it("never echoes passwords", () => {
    const s = reduce(open, {
      type: "sent",
      frame: { type: "login", name: "Ada", password: "correct horse" },
    });
    expect(JSON.stringify(s)).not.toContain("correct horse");
  });

  it("takes state frames whole and shows errors until the next action", () => {
    let s = reduce(open, {
      type: "frame",
      frame: {
        type: "state",
        tick: 3,
        place: { id: 1, name: "Hall", description: "Bare." },
        exits: ["out"],
        here: ["Bo"],
      },
    });
    expect([s.place?.name, s.exits, s.here]).toEqual(["Hall", ["out"], ["Bo"]]);
    s = reduce(s, { type: "frame", frame: { type: "error", code: "slow-down", message: "Too many." } });
    expect(s.error?.code).toBe("slow-down");
    s = reduce(s, { type: "sent", frame: { type: "command", text: "look" } });
    expect(s.error).toBeNull();
  });

  it("refuses a server speaking another protocol version", () => {
    const s = reduce(open, { type: "frame", frame: { type: "welcome", protocol: 2, engine: "9.9.9" } });
    expect(s.error?.code).toBe("protocol");
  });

  it("is signed out when kicked and notes disconnection", () => {
    let s = reduce(open, { type: "frame", frame: { type: "session", name: "Ada", character: 1 } });
    s = reduce(s, { type: "frame", frame: { type: "kicked", reason: "Signed in elsewhere." } });
    expect(s.signedIn).toBeNull();
    s = reduce(s, { type: "closed" });
    expect(s.connection).toBe("closed");
    expect(s.log.map((l) => l.text)).toEqual(["Signed in elsewhere.", "Disconnected."]);
  });

  it("keeps at most LOG_LIMIT lines", () => {
    let s = open;
    for (let i = 0; i < LOG_LIMIT + 20; i++) s = reduce(s, line(`line ${i}`));
    expect(s.log).toHaveLength(LOG_LIMIT);
    expect(s.log[0].text).toBe("line 20");
  });
});

describe("helpers", () => {
  it("parses only objects with a type", () => {
    expect(parseFrame('{"type":"kicked","reason":"x"}')).toEqual({ type: "kicked", reason: "x" });
    expect(parseFrame("[1,2]")).toBeNull();
    expect(parseFrame("not json")).toBeNull();
    expect(parseFrame('{"no":"type"}')).toBeNull();
  });

  it("builds the socket URL from the page", () => {
    expect(socketUrl({ protocol: "http:", host: "localhost:4700" })).toBe("ws://localhost:4700/ws");
    expect(socketUrl({ protocol: "https:", host: "play.example" })).toBe("wss://play.example/ws");
  });
});
