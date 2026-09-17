import { type FormEvent, useState } from "react";

import { submitsOnEnter } from "./keys";
import type { ClientFrame, LogLine } from "./protocol";

export interface SignInProps {
  disabled: boolean;
  send: (frame: ClientFrame) => void;
  log: LogLine[];
}

export function SignIn({ disabled, send, log }: SignInProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    send({ type: mode, name: name.trim(), password });
    setPassword("");
  };

  const notices = log.filter((line) => line.kind === "notice");

  return (
    <main className="signin">
      <form onSubmit={submit} onKeyDown={submitsOnEnter} aria-labelledby="signin-title">
        <h2 id="signin-title">{mode === "login" ? "Log in" : "Create a character"}</h2>
        <label>
          Name
          <input
            name="name"
            autoComplete="username"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={2}
            maxLength={24}
            pattern="[A-Za-z][A-Za-z0-9\-]{1,23}"
            title="2 to 24 letters, digits or hyphens, starting with a letter"
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            maxLength={128}
          />
        </label>
        <button type="submit" disabled={disabled}>
          {mode === "login" ? "Log in" : "Create character"}
        </button>
        <button
          type="button"
          className="link"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "New here? Create a character" : "Have a character? Log in"}
        </button>
      </form>
      {notices.length > 0 && <p className="notice">{notices[notices.length - 1].text}</p>}
    </main>
  );
}
