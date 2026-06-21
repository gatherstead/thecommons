import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Two-tier layout mirrors theCommonsWeb (16.7): a fast node tier for pure logic
// (no DOM) and a db tier on jsdom for component/hook tests. broadcastWeb uses
// plain fetch + React state — no QueryClient — so the setup stays minimal.
export default defineConfig({
  plugins: [react()],
  test: {
    projects: [
      {
        test: {
          name: "fast",
          environment: "node",
          include: ["src/**/*.fast.test.{ts,tsx}"],
        },
      },
      {
        test: {
          name: "db",
          environment: "jsdom",
          include: ["src/**/*.db.test.{ts,tsx}"],
          setupFiles: ["./vitest.setup.ts"],
        },
      },
    ],
  },
});
