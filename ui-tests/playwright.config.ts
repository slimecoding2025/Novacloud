import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  retries: 1,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.WEB_URL ?? "http://localhost:8080", trace: "retain-on-failure" },
});
