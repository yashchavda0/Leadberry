import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 120000,
  use: { baseURL: "http://127.0.0.1:3012", headless: true, trace: "off", screenshot: "off", video: "off" },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3012",
    url: "http://127.0.0.1:3012/login",
    reuseExistingServer: false,
    timeout: 120000,
    env: { CRM_BACKEND_URL: "http://127.0.0.1:8013", CRM_NEXT_DIST_DIR: ".next-e2e" },
  },
});
