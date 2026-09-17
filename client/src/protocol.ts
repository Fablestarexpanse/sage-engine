// sage.protocol/1 as the client sees it, and the state a session builds from its frames.
// Pure: no DOM, no sockets, so it is tested on its own.

export type ClientFrame =
  | { type: "register"; name: string; password: string }
  | { type: "login"; name: string; password: string }
  | { type: "command"; text: string };

export interface PlaceView {
  id: number;
  name: string;
  description: string;
}

export type ServerFrame =
  | { type: "welcome"; protocol: number; engine: string }
  | { type: "session"; name: string; character: number }
  | {
      type: "line";
      tick: number;
      key: string;
      params: Record<string, string>;
      text: string | null;
    }
  | {
      type: "state";
      tick: number;
      place: PlaceView | null;
      exits: string[];
      here: string[];
    }
  | { type: "error"; code: string; message: string }
  | { type: "kicked"; reason: string };

export const PROTOCOL = 1;

/// How many lines the log keeps.
export const LOG_LIMIT = 500;

export type Connection = "connecting" | "open" | "closed";

export interface LogLine {
  id: number;
  kind: "world" | "echo" | "notice";
  text: string;
}

export interface Session {
  connection: Connection;
  engine: string | null;
  signedIn: { name: string; character: number } | null;
  log: LogLine[];
  place: PlaceView | null;
  exits: string[];
  here: string[];
  error: { code: string; message: string } | null;
  nextLineId: number;
}

export const initialSession: Session = {
  connection: "connecting",
  engine: null,
  signedIn: null,
  log: [],
  place: null,
  exits: [],
  here: [],
  error: null,
  nextLineId: 1,
};

export type Action =
  | { type: "open" }
  | { type: "closed" }
  | { type: "frame"; frame: ServerFrame }
  | { type: "sent"; frame: ClientFrame }
  | { type: "dismiss-error" };

function append(session: Session, kind: LogLine["kind"], text: string): Session {
  const log = [...session.log, { id: session.nextLineId, kind, text }];
  return {
    ...session,
    log: log.length > LOG_LIMIT ? log.slice(log.length - LOG_LIMIT) : log,
    nextLineId: session.nextLineId + 1,
  };
}

export function reduce(session: Session, action: Action): Session {
  switch (action.type) {
    case "open":
      return { ...session, connection: "open" };
    case "closed":
      return append({ ...session, connection: "closed" }, "notice", "Disconnected.");
    case "dismiss-error":
      return { ...session, error: null };
    case "sent":
      return action.frame.type === "command"
        ? append({ ...session, error: null }, "echo", `> ${action.frame.text}`)
        : { ...session, error: null };
    case "frame":
      return receive(session, action.frame);
  }
}

function receive(session: Session, frame: ServerFrame): Session {
  switch (frame.type) {
    case "welcome":
      if (frame.protocol !== PROTOCOL) {
        return {
          ...session,
          error: {
            code: "protocol",
            message: `This client speaks protocol ${PROTOCOL}; the server speaks ${frame.protocol}.`,
          },
        };
      }
      return { ...session, engine: frame.engine };
    case "session":
      return {
        ...session,
        signedIn: { name: frame.name, character: frame.character },
        error: null,
      };
    case "line":
      // A line the world has no wording for is not meant to be shown.
      return frame.text === null ? session : append(session, "world", frame.text);
    case "state":
      return { ...session, place: frame.place, exits: frame.exits, here: frame.here };
    case "error":
      return { ...session, error: { code: frame.code, message: frame.message } };
    case "kicked":
      return append({ ...session, signedIn: null }, "notice", frame.reason);
  }
}

/// Parses a server frame, or returns null for anything that is not one.
export function parseFrame(text: string): ServerFrame | null {
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value === "object" && value !== null && "type" in value) {
      return value as ServerFrame;
    }
  } catch {
    // fall through
  }
  return null;
}

/// The WebSocket URL for a page served by the engine.
export function socketUrl(location: { protocol: string; host: string }): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws`;
}
