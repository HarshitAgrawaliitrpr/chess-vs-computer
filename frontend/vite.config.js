import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vite config + Vitest config (single file).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Dev only: forward API calls to the FastAPI backend.
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/__tests__/**/*.test.{js,jsx}"],
    restoreMocks: true,
  },
});