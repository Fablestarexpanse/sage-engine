import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin proxy in dev: browser → :5173/__nexus/* → Nexus :8001 (HTTP + WS). Avoids direct loopback quirks in some browsers.
const NEXUS_TARGET = `http://127.0.0.1:${process.env.VITE_NEXUS_PORT || '8001'}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/__nexus': {
        target: NEXUS_TARGET,
        changeOrigin: true,
        ws: true,
        // Pass the browser's address on (X-Forwarded-For), so Nexus can tell a browser on this
        // machine from one on the network reaching the dev server through --host.
        xfwd: true,
        rewrite: (path) => path.replace(/^\/__nexus/, ''),
      },
    },
  },
})
