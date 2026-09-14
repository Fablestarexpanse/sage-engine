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
      proxy: {
        "/play": { target, changeOrigin: true },
        "/media": { target, changeOrigin: true },
        "/ws/play": { target: `ws://127.0.0.1:${nexusPort}`, ws: true },
      },
    },
  };
});
