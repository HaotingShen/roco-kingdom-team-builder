import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  // TapTap requires relative asset paths (./assets/...) so the zip upload works
  // from any subdirectory on 3rd-tool-h5-al.tapimg.com
  base: mode === "taptap" ? "./" : "/",
  ...(mode === "taptap" && {
    build: {
      rollupOptions: {
        input: path.resolve(__dirname, "index.taptap.html"),
      },
    },
  }),
  server: {
    host: true,
    port: 5173,
    open: true,
    watch: { usePolling: true, interval: 100 },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
}));