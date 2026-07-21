import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventDraft } from "../../models/broadcastModels";
import {
  ApiError,
  type ApiAuth,
  aiAutofill,
  authHeaders,
  cancelJob,
  directSubmit,
  getAccess,
  getJob,
  getManualRecipe,
  openScreenshot,
  previewBroadcast,
  retryJob,
  submitBroadcast,
  submitReal,
} from "../broadcastApi";

// The module falls back to this when VITE_BROADCAST_API_BASE_URL is unset, which
// it is under test.
const BASE = "http://127.0.0.1:8000";

const EVENT: EventDraft = {
  draft_id: "draft-uuid-123",
  title: "Test Event",
  description: "A description",
  start_datetime: "2026-10-17T16:00:00.000Z",
  all_day: false,
  venue_name: "Some Venue",
  address_line1: "1 Main St",
  state: "NC",
  zip: "27701",
  locality: ["durham"],
  categories: ["music"],
  is_free: true,
};

const CODE: ApiAuth = { accessCode: "CODE" };
const JWT_AUTH: ApiAuth = { jwt: "tok.en.here" };

const jsonResponse = (
  body: unknown,
  { ok = true, status = 200 }: { ok?: boolean; status?: number } = {},
) => ({ ok, status, json: () => Promise.resolve(body) });

const lastCall = (mock: ReturnType<typeof vi.fn>) =>
  mock.mock.calls[mock.mock.calls.length - 1] as [string, RequestInit];

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── authHeaders unit tests ─────────────────────────────────────────────────

describe("authHeaders", () => {
  it("returns Bearer header for a JWT", () => {
    expect(authHeaders({ jwt: "my-token" })).toEqual({ Authorization: "Bearer my-token" });
  });

  it("returns X-Broadcast-Access-Code header for an access code", () => {
    expect(authHeaders({ accessCode: "MY-CODE" })).toEqual({
      "X-Broadcast-Access-Code": "MY-CODE",
    });
  });

  it("JWT wins when both are provided", () => {
    expect(authHeaders({ jwt: "jwt", accessCode: "code" })).toEqual({
      Authorization: "Bearer jwt",
    });
  });

  it("returns empty object when neither is set", () => {
    expect(authHeaders({})).toEqual({});
  });
});

// ── getAccess ─────────────────────────────────────────────────────────────

describe("getAccess", () => {
  it("GETs /broadcast/access with Bearer header and returns tier info", async () => {
    const result = { tier: 2 as const, is_trial: false, uses_remaining: null };
    fetchMock.mockResolvedValue(jsonResponse(result));

    await expect(getAccess(JWT_AUTH)).resolves.toEqual(result);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/access`);
    expect(init.method).toBeUndefined();
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok.en.here");
  });

  it("GETs /broadcast/access with access-code header", async () => {
    const result = { tier: 1 as const, is_trial: true, uses_remaining: 3 };
    fetchMock.mockResolvedValue(jsonResponse(result));

    await expect(getAccess(CODE)).resolves.toEqual(result);

    const [, init] = lastCall(fetchMock);
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
  });

  it("throws ApiError on 403, surfacing the backend detail", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: "This access code has expired — please contact support." },
        { ok: false, status: 403 },
      ),
    );

    await expect(getAccess(JWT_AUTH)).rejects.toMatchObject({
      status: 403,
      message: "This access code has expired — please contact support.",
    });
  });

  it("returns tier 0 for anonymous (no-credentials) request", async () => {
    const result = { tier: 0 as const, is_trial: false, uses_remaining: null };
    fetchMock.mockResolvedValue(jsonResponse(result));

    await expect(getAccess({})).resolves.toEqual(result);

    const [, init] = lastCall(fetchMock);
    // No auth header
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBeUndefined();
  });
});

// ── POST wrappers ──────────────────────────────────────────────────────────

describe("POST wrappers", () => {
  it("previewBroadcast sends auth header and {draft_id, event} body", async () => {
    const result = { eligible: [{ site_key: "a", name: "A" }], excluded: [] };
    fetchMock.mockResolvedValue(jsonResponse(result));

    await expect(previewBroadcast(CODE, EVENT)).resolves.toEqual(result);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/preview`);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ draft_id: EVENT.draft_id, event: EVENT });
    // Must not include access_code in the body
    expect(body).not.toHaveProperty("access_code");
  });

  it("previewBroadcast sends Bearer header when using JWT auth", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ eligible: [], excluded: [] }));

    await previewBroadcast(JWT_AUTH, EVENT);

    const [, init] = lastCall(fetchMock);
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok.en.here");
  });

  it("submitBroadcast sends event + site_keys + dry_run (no access_code in body)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1" }));

    await submitBroadcast(CODE, EVENT, ["a", "b"], true);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/submit`);
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ event: EVENT, site_keys: ["a", "b"], dry_run: true });
    expect(body).not.toHaveProperty("access_code");
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
  });

  it("retryJob targets the job's retry route without access_code in body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", requeued: 2 }));

    await retryJob(CODE, "j1", ["a", "b"]);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/retry`);
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ site_keys: ["a", "b"] });
    expect(body).not.toHaveProperty("access_code");
  });

  it("submitReal targets the submit-real route without access_code in body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", submitted: 1 }));

    await submitReal(CODE, "j1", ["a"]);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/submit-real`);
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ site_keys: ["a"] });
    expect(body).not.toHaveProperty("access_code");
  });

  it("cancelJob posts empty body (auth in header)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", status: "canceled", skipped: 3 }));

    await cancelJob(CODE, "j1");

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/cancel`);
    const body = JSON.parse(init.body as string);
    expect(body).not.toHaveProperty("access_code");
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
  });

  it("directSubmit posts draft_id + event to /api/events/direct-submit (no access_code in body)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "accepted", draft_id: "draft-uuid-123" }));

    await directSubmit(CODE, "draft-uuid-123", EVENT);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/api/events/direct-submit`);
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ draft_id: "draft-uuid-123", event: EVENT });
    expect(body).not.toHaveProperty("access_code");
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
  });
});

describe("aiAutofill", () => {
  it("POSTs to /broadcast/ai-autofill with auth header and text, no access_code in body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ event: EVENT }));

    const result = await aiAutofill(CODE, "paste event text here");

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/ai-autofill`);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Broadcast-Access-Code"]).toBe("CODE");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ text: "paste event text here" });
    expect(body).not.toHaveProperty("access_code");
    expect(result).toEqual({ event: EVENT });
  });

  it("maps 400 (blank text) to an error", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ text: ["blank"] }, { ok: false, status: 400 }));

    await expect(aiAutofill(CODE, "")).rejects.toMatchObject({
      status: 400,
      message: expect.stringContaining("problem"),
    });
  });

  it("maps 403 (bad access / rate limit) to the access-denied message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 403 }));

    await expect(aiAutofill({ accessCode: "BAD" }, "some text")).rejects.toMatchObject({
      status: 403,
      message: expect.stringContaining("Access denied"),
    });
  });

  it("maps 502 (LLM down) to a generic failure message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 502 }));

    const err = await aiAutofill(CODE, "text").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
  });
});

describe("GET wrappers", () => {
  it("getJob sends X-Broadcast-Access-Code header (access-code auth)", async () => {
    const job = { job_id: "j1", status: "queued", targets: [] };
    fetchMock.mockResolvedValue(jsonResponse(job));

    await expect(getJob(CODE, "j1")).resolves.toEqual(job);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1`);
    expect(init.method).toBeUndefined();
    expect(init.headers).toEqual({ "X-Broadcast-Access-Code": "CODE" });
    expect(init.body).toBeUndefined();
  });

  it("getJob sends Bearer header when using JWT auth", async () => {
    const job = { job_id: "j1", status: "queued", targets: [] };
    fetchMock.mockResolvedValue(jsonResponse(job));

    await getJob(JWT_AUTH, "j1");

    const [, init] = lastCall(fetchMock);
    expect(init.headers).toEqual({ Authorization: "Bearer tok.en.here" });
  });

  it("getManualRecipe fetches the per-site recipe with the access header", async () => {
    const recipe = { site_key: "a", name: "A", url: "u", fields: [], captcha_hint: null, submit_selector: "#go" };
    fetchMock.mockResolvedValue(jsonResponse(recipe));

    await expect(getManualRecipe(CODE, "j1", "siteA")).resolves.toEqual(recipe);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/manual/siteA`);
    expect(init.headers).toEqual({ "X-Broadcast-Access-Code": "CODE" });
  });
});

describe("error mapping", () => {
  it("maps 403 to the access-denied message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 403 }));

    await expect(previewBroadcast({ accessCode: "BAD" }, EVENT)).rejects.toMatchObject({
      status: 403,
      message: expect.stringContaining("Access denied"),
    });
  });

  it("maps 400 to a form-problem message echoing the body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ zip: ["required"] }, { ok: false, status: 400 }));

    await expect(previewBroadcast(CODE, EVENT)).rejects.toMatchObject({
      status: 400,
      message: expect.stringContaining("zip"),
    });
  });

  it("maps other failures to a generic message and throws ApiError", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));

    const error = await getJob(CODE, "j1").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(500);
    expect(error.message).toBe("Request failed (500).");
  });
});

describe("openScreenshot", () => {
  it("fetches the bytes and opens a blob URL in a new tab", async () => {
    const blob = new Blob(["x"]);
    fetchMock.mockResolvedValue({ ok: true, status: 200, blob: () => Promise.resolve(blob) });
    const openMock = vi.fn();
    const createObjectURL = vi.fn(() => "blob:fake");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("window", { open: openMock });
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.useFakeTimers();

    await openScreenshot(CODE, "/broadcast/jobs/j1/shot.png");

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/shot.png`);
    expect(init.headers).toEqual({ "X-Broadcast-Access-Code": "CODE" });
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(openMock).toHaveBeenCalledWith("blob:fake", "_blank", "noopener");

    vi.advanceTimersByTime(60_000);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake");
    vi.useRealTimers();
  });

  it("throws ApiError when the screenshot fetch fails", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 });

    await expect(openScreenshot(CODE, "/x.png")).rejects.toBeInstanceOf(ApiError);
  });
});
