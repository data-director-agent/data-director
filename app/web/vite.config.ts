import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The app's Python server (`uv run data-director`) serves /api; `npm run dev` proxies to it.
const API = process.env.DD_APP_URL ?? "http://127.0.0.1:7860";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": API } },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
