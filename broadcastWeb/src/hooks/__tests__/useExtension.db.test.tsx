import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

// useExtension reads VITE_BROADCAST_EXTENSION_ID once at module load, so each
// test stubs the env then dynamically imports a fresh copy of the module.
async function loadHook() {
  const mod = await import("../useExtension");
  return mod.useExtension;
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("useExtension", () => {
  it("flips installed to true when the extension answers a ping", async () => {
    vi.stubEnv("VITE_BROADCAST_EXTENSION_ID", "ext-123");
    const sendMessage = vi.fn(
      (_id: string, _msg: unknown, cb: (r?: { ok: boolean }) => void) => cb({ ok: true }),
    );
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const useExtension = await loadHook();
    const { result } = renderHook(() => useExtension());

    await waitFor(() => expect(result.current.installed).toBe(true));
    expect(result.current.extensionId).toBe("ext-123");
    expect(sendMessage).toHaveBeenCalledWith("ext-123", { type: "ping" }, expect.any(Function));
  });

  it("resolves to whichever of several comma-separated ids answers", async () => {
    vi.stubEnv("VITE_BROADCAST_EXTENSION_ID", "dev-unpacked, jidmhdmlbjfnblbheglmodhpcjhafjmi");
    // Only the published id answers ok; the dev one reports "no receiving end".
    const sendMessage = vi.fn(
      (id: string, _msg: unknown, cb: (r?: { ok: boolean }) => void) =>
        cb(id === "jidmhdmlbjfnblbheglmodhpcjhafjmi" ? { ok: true } : undefined),
    );
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const useExtension = await loadHook();
    const { result } = renderHook(() => useExtension());

    await waitFor(() => expect(result.current.installed).toBe(true));
    expect(result.current.extensionId).toBe("jidmhdmlbjfnblbheglmodhpcjhafjmi");
    expect(sendMessage).toHaveBeenCalledWith("dev-unpacked", { type: "ping" }, expect.any(Function));
    expect(sendMessage).toHaveBeenCalledWith(
      "jidmhdmlbjfnblbheglmodhpcjhafjmi", { type: "ping" }, expect.any(Function),
    );
  });

  it("stays not-installed in a non-Chromium environment", async () => {
    vi.stubEnv("VITE_BROADCAST_EXTENSION_ID", "ext-123");
    // No window.chrome — getRuntime() returns undefined.

    const useExtension = await loadHook();
    const { result } = renderHook(() => useExtension());

    // Give any pending effect a chance to run; installed must remain false.
    await Promise.resolve();
    expect(result.current.installed).toBe(false);
  });

  it("stays not-installed when no extension id is configured", async () => {
    vi.stubEnv("VITE_BROADCAST_EXTENSION_ID", "");
    const sendMessage = vi.fn();
    vi.stubGlobal("chrome", { runtime: { sendMessage } });

    const useExtension = await loadHook();
    const { result } = renderHook(() => useExtension());

    await Promise.resolve();
    expect(result.current.installed).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();
  });
});
