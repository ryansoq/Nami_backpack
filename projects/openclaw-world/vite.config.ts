import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: "src",
  publicDir: resolve(__dirname, "public"),
  server: {
    port: 3000,
    allowedHosts: true,
    proxy: {
      "/ws": {
        target: "ws://localhost:18800",
        ws: true,
      },
      "/api/ipc": {
        target: "http://localhost:18800",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/ipc/, '/ipc'),
      },
    },
  },
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: true,
  },
});
