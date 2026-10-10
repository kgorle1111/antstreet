import { defineConfig, devices } from "@playwright/test";

// Runs against the built site (`npm run build` first), served by `astro preview`.
export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://localhost:4321/antstreet/", ...devices["Desktop Chrome"] },
  webServer: {
    command: "npm run preview",
    url: "http://localhost:4321/antstreet/",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
