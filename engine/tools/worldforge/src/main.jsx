import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { ThemeProvider } from "./ThemeContext.jsx";
import "./index.css";

function showFatal(message, detail) {
  const root = document.getElementById("root");
  if (!root) return;
  root.innerHTML = "";
  const pre = document.createElement("pre");
  pre.style.cssText =
    "padding:16px;font:13px/1.45 system-ui,Segoe UI,sans-serif;white-space:pre-wrap;word-break:break-word;color:#c00;background:#1a0a0a;margin:0;height:100vh;box-sizing:border-box";
  pre.textContent = `${message}${detail ? `\n\n${detail}` : ""}`;
  root.appendChild(pre);
}

window.addEventListener("error", (ev) => {
  // ResizeObserver loop warnings are benign browser noise from ReactFlow —
  // they fire when the canvas resizes faster than the observer can flush.
  if (ev.message?.includes("ResizeObserver loop")) return;
  showFatal(ev.message, ev.error?.stack || `${ev.filename}:${ev.lineno}`);
});
window.addEventListener("unhandledrejection", (ev) => {
  const r = ev.reason;
  showFatal(r instanceof Error ? r.message : String(r), r instanceof Error ? r.stack : "");
});

const el = document.getElementById("root");
if (!el) {
  document.body.textContent = "Missing #root";
} else {
  try {
    ReactDOM.createRoot(el).render(
      <React.StrictMode>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </React.StrictMode>
    );
  } catch (e) {
    showFatal(e instanceof Error ? e.message : String(e), e instanceof Error ? e.stack : "");
  }
}
