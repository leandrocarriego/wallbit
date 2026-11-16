import { defineConfig } from "@playwright/test";

// E2E against the running compose stack (`make up`). The spec reseeds the demo data first.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", viewport: { width: 1440, height: 1000 } },
  reporter: "list",
});
