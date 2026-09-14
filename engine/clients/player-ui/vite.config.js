import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const nexusPort = env.VITE_NEXUS_PORT || "8001";
  const target = `http://127.0.0.1:${nexusPort}`;

  return {
    plugins: [react()],
    server: {
      // xfwd: pass the browser's address on (X-Forwarded-For), so Nexus can tell a browser on this
      // machine from one on the network reaching the dev server through --host.
      proxy: {
        "/play": { target, changeOrigin: true, xfwd: true },
        "/media": { target, changeOrigin: true, xfwd: true },
        "/ws/play": { target: `ws://127.0.0.1:${nexusPort}`, ws: true, xfwd: true },
      },
    },
  };
});
