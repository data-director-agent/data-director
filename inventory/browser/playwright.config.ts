import { defineConfig, devices } from "@playwright/test";

// The browser scanner in a real browser (README.md, Browser scanner): the test page is built and
// previewed with the bundle by `e2e/vite.config.ts`. Run `npm run bundle` first.
const PORT = 4174;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Starting Python and installing the bundle takes a few seconds before any file is read.
  timeout: 120_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: `vite build --config e2e/vite.config.ts && vite preview --config e2e/vite.config.ts --host 127.0.0.1 --port ${PORT} --strictPort`,
    timeout: 120_000,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
  },
});
