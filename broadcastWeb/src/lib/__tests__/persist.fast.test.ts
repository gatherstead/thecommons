import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { JobDetail } from "../../models/broadcastModels";
import {
  clearDraft,
  DRAFT_KEY,
  loadDraft,
  loadSession,
  saveDraft,
  saveSession,
  SESSION_KEY,
  type DraftBundle,
  type SessionBundle,
} from "../persist";

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

describe("session scope", () => {
  it("saves and restores the access code, verified flag, and contact details", () => {
    const session: SessionBundle = {
      accessCode: "CODE",
      verified: true,
      organizer_name: "The Org",
      contact_email: "a@b.com",
      contact_phone: "919-555-0100",
    };
    saveSession(session);
    expect(loadSession()).toEqual(session);
  });

  it("returns an empty session when nothing is stored", () => {
    expect(loadSession()).toEqual({});
  });

  it("returns an empty session when stored JSON is corrupt", () => {
    localStorage.setItem(SESSION_KEY, "{not json");
    expect(loadSession()).toEqual({});
  });
});

describe("draft scope", () => {
  it("saves and restores an in-progress draft", () => {
    const draft: DraftBundle = {
      draft: undefined,
      preview: null,
      selected: ["a", "b"],
      job: jobWith("running"),
      jobId: "j1",
    };
    saveDraft(draft);
    expect(loadDraft()).toEqual(draft);
  });

  it.each(["done", "failed", "canceled"] as const)(
    "still restores the draft once the job is %s (no auto-wipe)",
    (status) => {
      saveDraft({ selected: ["a"], job: jobWith(status), jobId: "j1" });
      expect(loadDraft().job?.status).toBe(status);
    },
  );

  it("returns an empty draft when nothing is stored", () => {
    expect(loadDraft()).toEqual({});
  });

  it("returns an empty draft when stored JSON is corrupt", () => {
    localStorage.setItem(DRAFT_KEY, "{not json");
    expect(loadDraft()).toEqual({});
  });
});

describe("clearDraft", () => {
  it("removes the draft but leaves the session intact", () => {
    saveSession({ accessCode: "CODE", verified: true });
    saveDraft({ job: jobWith("running"), jobId: "j1" });

    clearDraft();

    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
    expect(loadDraft()).toEqual({});
    expect(loadSession()).toEqual({ accessCode: "CODE", verified: true });
  });
});

describe("legacy migration", () => {
  it("seeds both scopes from the old fused bundle when new keys are absent", () => {
    localStorage.setItem(
      "broadcast:state:v1",
      JSON.stringify({
        accessCode: "OLD",
        verified: true,
        draft: { organizer_name: "Old Org", contact_email: "old@b.com" },
        selected: ["x"],
        job: jobWith("queued"),
        jobId: "old-job",
      }),
    );

    expect(loadSession()).toEqual({
      accessCode: "OLD",
      verified: true,
      organizer_name: "Old Org",
      contact_email: "old@b.com",
      contact_phone: undefined,
    });
    expect(loadDraft().jobId).toBe("old-job");
    expect(loadDraft().selected).toEqual(["x"]);
  });

  it("prefers the new keys over the legacy bundle", () => {
    localStorage.setItem("broadcast:state:v1", JSON.stringify({ accessCode: "OLD" }));
    saveSession({ accessCode: "NEW", verified: false });

    expect(loadSession().accessCode).toBe("NEW");
  });
});
