import { defineConfig } from "@playwright/test";

const port = Number(process.env.CRM_TEST_PORT || 3012);

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 120000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  webServer: {
    command: `node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/login`,
    reuseExistingServer: false,
    timeout: 120000,
    env: {
      CRM_BACKEND_URL: "http://127.0.0.1:8013",
      CRM_NEXT_DIST_DIR: `.next-e2e-${port}`,
    },
  },
});
