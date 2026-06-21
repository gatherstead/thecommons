import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { JobDetail } from "../../models/broadcastModels";
import { loadBundle, saveBundle, STORAGE_KEY, type PersistBundle } from "../persist";

// Minimal in-memory localStorage so the round-trip runs in the node (fast) tier
// without a DOM.
function makeStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (k) => (store.has(k) ? store.get(k)! : null),
    setItem: (k, v) => void store.set(k, String(v)),
    removeItem: (k) => void store.delete(k),
    clear: () => store.clear(),
    key: (i) => [...store.keys()][i] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
}

const jobWith = (status: JobDetail["status"]): JobDetail => ({
  job_id: "j1",
  status,
  created_at: "",
  started_at: null,
  finished_at: null,
  targets: [],
});

beforeEach(() => {
  vi.stubGlobal("localStorage", makeStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("persist round-trip", () => {
  it("saves and restores a bundle for unfinished work", () => {
    const bundle: PersistBundle = {
      accessCode: "CODE",
      verified: true,
      draft: undefined,
      preview: null,
      selected: ["a", "b"],
      job: jobWith("running"),
      jobId: "j1",
    };

    saveBundle(bundle);

    expect(loadBundle()).toEqual(bundle);
  });

  it("returns an empty bundle when nothing is stored", () => {
    expect(loadBundle()).toEqual({});
  });

  it("returns an empty bundle when stored JSON is corrupt", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");

    expect(loadBundle()).toEqual({});
  });
});

describe("clearing on terminal status", () => {
  it.each(["done", "failed", "canceled"] as const)(
    "drops saved state once the job is %s",
    (status) => {
      saveBundle({ accessCode: "CODE", job: jobWith("running") });
      expect(loadBundle()).not.toEqual({});

      saveBundle({ accessCode: "CODE", job: jobWith(status) });

      expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
      expect(loadBundle()).toEqual({});
    },
  );

  it("keeps state while the job is still queued", () => {
    saveBundle({ accessCode: "CODE", job: jobWith("queued") });

    expect(loadBundle().job?.status).toBe("queued");
  });
});
