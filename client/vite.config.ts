import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// `pnpm dev` proxies /ws to a local `sage run --listen 127.0.0.1:4700`.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/ws": { target: "ws://127.0.0.1:4700", ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // No inline scripts or styles, so the engine can serve a strict Content-Security-Policy.
    assetsInlineLimit: 0,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test-setup.ts"],
  },
});
