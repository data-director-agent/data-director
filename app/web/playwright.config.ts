import { defineConfig, devices } from "@playwright/test";

// Browser tests run against the built shell (`vite preview`), with `/api/agents` answered from
// the fixtures the Python tests keep current (app/tests/test_app.py). No Python server is needed.
const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  // Describing a folder runs the browser scanner, whose support differs by browser engine (#554),
  // so its test runs in Firefox and WebKit too. The rest of the shell is tested in Chromium.
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", testMatch: "scan.spec.ts", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", testMatch: "scan.spec.ts", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    timeout: 120_000,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
  },
});
