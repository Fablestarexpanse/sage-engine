import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { submitsOnEnter } from "./keys";
import type { ClientFrame, Session } from "./protocol";

export interface PlayProps {
  session: Session;
  send: (frame: ClientFrame) => void;
}

/// Most commands kept for arrow-key recall.
const HISTORY_LIMIT = 100;

export function Play({ session, send }: PlayProps) {
  const [text, setText] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [recall, setRecall] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLLIElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [session.log.length]);

  const command = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    send({ type: "command", text: trimmed });
    setHistory((h) => [...h.slice(-(HISTORY_LIMIT - 1)), trimmed]);
    setRecall(null);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    command(text);
    setText("");
  };

  const keys = (event: KeyboardEvent<HTMLInputElement>) => {
    if (submitsOnEnter(event)) return;
    if (history.length === 0) return;
    if (event.key === "ArrowUp") {
      event.preventDefault();
      const next = recall === null ? history.length - 1 : Math.max(0, recall - 1);
      setRecall(next);
      setText(history[next]);
    } else if (event.key === "ArrowDown" && recall !== null) {
      event.preventDefault();
      const next = recall + 1;
      if (next >= history.length) {
        setRecall(null);
        setText("");
      } else {
        setRecall(next);
        setText(history[next]);
      }
    }
  };

  const go = (exit: string) => {
    command(exit);
    input.current?.focus();
  };

  return (
    <main className="play">
      <section className="world" aria-label="What you perceive">
        <ol className="log" role="log" aria-live="polite">
          {session.log.map((line) => (
            <li key={line.id} className={`line line-${line.kind}`}>
              {line.text}
            </li>
          ))}
          <li ref={end} aria-hidden="true" className="end" />
        </ol>
        <form className="command" onSubmit={submit}>
          <label htmlFor="command-input" className="visually-hidden">
            Command
          </label>
          <input
            id="command-input"
            ref={input}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={keys}
            autoComplete="off"
            spellCheck={false}
            maxLength={512}
            placeholder="Type a command: look, say hello, go …"
            disabled={session.connection !== "open"}
            autoFocus
          />
          <button type="submit" disabled={session.connection !== "open"}>
            Send
          </button>
        </form>
      </section>
      <aside className="panel" aria-label="Where you are">
        <h2>{session.place?.name ?? "Nowhere"}</h2>
        {session.place?.description && <p>{session.place.description}</p>}
        <h3>Ways on</h3>
        {session.exits.length === 0 ? (
          <p>None.</p>
        ) : (
          <ul className="exits">
            {session.exits.map((exit) => (
              <li key={exit}>
                <button type="button" onClick={() => go(exit)} disabled={session.connection !== "open"}>
                  {exit}
                </button>
              </li>
            ))}
          </ul>
        )}
        <h3>Here</h3>
        {session.here.length === 0 ? (
          <p>No one else.</p>
        ) : (
          <ul className="here">
            {session.here.map((name, i) => (
              <li key={`${name}-${i}`}>{name}</li>
            ))}
          </ul>
        )}
      </aside>
    </main>
  );
}
