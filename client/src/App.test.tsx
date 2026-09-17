import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

/// A WebSocket that records what the app sends and lets a test play the server.
class FakeSocket {
  static last: FakeSocket | null = null;
  static OPEN = 1;
  readyState = 0;
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(public url: string) {
    FakeSocket.last = this;
  }

  send(data: string) {
    this.sent.push(JSON.parse(data));
  }

  close() {
    this.readyState = 3;
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
    this.server({ type: "welcome", protocol: 1, engine: "0.0.1" });
  }

  server(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function socket(): FakeSocket {
  if (!FakeSocket.last) throw new Error("no socket");
  return FakeSocket.last;
}

describe("App", () => {
  it("creates a character, then plays by keyboard and by exit buttons", async () => {
    const user = userEvent.setup();
    render(<App url="ws://test/ws" />);
    act(() => socket().open());

    await user.click(screen.getByRole("button", { name: /create a character/i }));
    await user.type(screen.getByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Password"), "correct horse");
    await user.click(screen.getByRole("button", { name: "Create character" }));
    expect(socket().sent).toEqual([{ type: "register", name: "Ada", password: "correct horse" }]);

    act(() => {
      socket().server({ type: "session", name: "Ada", character: 9 });
      socket().server({
        type: "state",
        tick: 1,
        place: { id: 1, name: "First place", description: "An empty place." },
        exits: ["onward"],
        here: ["Bo"],
      });
      socket().server({ type: "line", tick: 1, key: "sage.look.place", params: {}, text: "First place\nAn empty place." });
    });

    expect(screen.getByText("Playing as Ada")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "First place" })).toBeInTheDocument();
    expect(screen.getByRole("log")).toHaveTextContent("An empty place.");

    const input = screen.getByLabelText("Command");
    expect(input).toHaveFocus();
    await user.type(input, "say hello{Enter}");
    await user.type(input, "look{Enter}");
    await user.keyboard("{ArrowUp}{ArrowUp}");
    expect(input).toHaveValue("say hello");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(input).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "onward" }));
    expect(socket().sent.slice(1)).toEqual([
      { type: "command", text: "say hello" },
      { type: "command", text: "look" },
      { type: "command", text: "onward" },
    ]);
    expect(screen.getByRole("log")).toHaveTextContent("> say hello");

    // Enter that arrives as keydown alone, with no keypress after it, still sends once.
    fireEvent.change(input, { target: { value: "emote waves" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(socket().sent.slice(4)).toEqual([{ type: "command", text: "emote waves" }]);
    expect(input).toHaveValue("");
  });

  it("logs in on a bare Enter keydown, once", () => {
    render(<App url="ws://test/ws" />);
    act(() => socket().open());
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Ada" } });
    const password = screen.getByLabelText("Password");
    fireEvent.change(password, { target: { value: "correct horse" } });
    fireEvent.keyDown(password, { key: "Enter" });
    expect(socket().sent).toEqual([{ type: "login", name: "Ada", password: "correct horse" }]);
  });

  it("shows refusals and lets the player reconnect", async () => {
    const user = userEvent.setup();
    render(<App url="ws://test/ws" />);
    const first = socket();
    act(() => first.open());

    act(() => first.server({ type: "error", code: "bad-login", message: "That name and password do not match." }));
    expect(screen.getByRole("alert")).toHaveTextContent("do not match");

    act(() => first.onclose?.());
    expect(screen.getByRole("status")).toHaveTextContent("Disconnected");
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    expect(socket()).not.toBe(first);
  });
});
