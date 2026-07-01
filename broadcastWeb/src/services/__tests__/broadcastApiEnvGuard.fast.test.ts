import { afterEach, describe, expect, it, vi } from "vitest";

// Regression test: broadcastWeb/.env on the VM once had
// VITE_BROADCAST_API_BASE_URL=https:api.thecommons.town (missing "//"), which
// silently resolved as a relative URL against the SPA's own origin instead of
// the API host. broadcastApi.ts now validates the value at module load and
// throws instead of accepting it silently.
describe("VITE_BROADCAST_API_BASE_URL validation", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("throws at import time for a malformed value (missing //)", async () => {
    vi.stubEnv("VITE_BROADCAST_API_BASE_URL", "https:api.thecommons.town");
    await expect(import("../broadcastApi")).rejects.toThrow(/not a valid absolute URL/);
  });

  it("loads fine for a well-formed value", async () => {
    vi.stubEnv("VITE_BROADCAST_API_BASE_URL", "https://api.thecommons.town");
    await expect(import("../broadcastApi")).resolves.toBeDefined();
  });
});
