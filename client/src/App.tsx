import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { Play } from "./Play";
import {
  type ClientFrame,
  initialSession,
  parseFrame,
  reduce,
  socketUrl,
} from "./protocol";
import { SignIn } from "./SignIn";

export interface AppProps {
  /// Where to connect; defaults to /ws on the serving host.
  url?: string;
}

export function App({ url }: AppProps) {
  const [session, dispatch] = useReducer(reduce, initialSession);
  const socket = useRef<WebSocket | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ws = new WebSocket(url ?? socketUrl(window.location));
    socket.current = ws;
    ws.onopen = () => dispatch({ type: "open" });
    ws.onclose = () => dispatch({ type: "closed" });
    ws.onmessage = (event) => {
      const frame = typeof event.data === "string" ? parseFrame(event.data) : null;
      if (frame) dispatch({ type: "frame", frame });
    };
    return () => {
      ws.onclose = null;
      ws.close();
    };
  }, [url, attempt]);

  const send = useCallback((frame: ClientFrame) => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(frame));
      dispatch({ type: "sent", frame });
    }
  }, []);

  return (
    <div className="app">
      <header className="bar">
        <h1>SAGE</h1>
        <span className={`status status-${session.connection}`} role="status">
          {session.connection === "open" ? "Connected" : session.connection === "connecting" ? "Connecting…" : "Disconnected"}
        </span>
        {session.signedIn && <span className="who">Playing as {session.signedIn.name}</span>}
        {session.connection === "closed" && (
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Reconnect
          </button>
        )}
      </header>
      {session.error && (
        <div className="error" role="alert">
          <span>{session.error.message}</span>
          <button type="button" onClick={() => dispatch({ type: "dismiss-error" })} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}
      {session.signedIn ? (
        <Play session={session} send={send} />
      ) : (
        <SignIn disabled={session.connection !== "open"} send={send} log={session.log} />
      )}
    </div>
  );
}
