import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventDraft } from "../../models/broadcastModels";
import {
  ApiError,
  aiAutofill,
  cancelJob,
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

describe("POST wrappers", () => {
  it("previewBroadcast posts the access code + event and returns the body", async () => {
    const result = { eligible: [{ site_key: "a", name: "A" }], excluded: [] };
    fetchMock.mockResolvedValue(jsonResponse(result));

    await expect(previewBroadcast("CODE", EVENT)).resolves.toEqual(result);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/preview`);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      access_code: "CODE",
      event: EVENT,
    });
  });

  it("submitBroadcast includes site keys and the dry_run flag", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1" }));

    await submitBroadcast("CODE", EVENT, ["a", "b"], true);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/submit`);
    expect(JSON.parse(init.body as string)).toEqual({
      access_code: "CODE",
      event: EVENT,
      site_keys: ["a", "b"],
      dry_run: true,
    });
  });

  it("retryJob targets the job's retry route", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", requeued: 2 }));

    await retryJob("CODE", "j1", ["a", "b"]);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/retry`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      access_code: "CODE",
      site_keys: ["a", "b"],
    });
  });

  it("submitReal targets the submit-real route", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", submitted: 1 }));

    await submitReal("CODE", "j1", ["a"]);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/submit-real`);
    expect(JSON.parse(init.body as string)).toEqual({
      access_code: "CODE",
      site_keys: ["a"],
    });
  });

  it("cancelJob posts only the access code", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ job_id: "j1", status: "canceled", skipped: 3 }));

    await cancelJob("CODE", "j1");

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/cancel`);
    expect(JSON.parse(init.body as string)).toEqual({ access_code: "CODE" });
  });
});

describe("aiAutofill", () => {
  it("POSTs to /broadcast/ai-autofill with access_code and text, returns the event", async () => {
    const eventPayload: EventDraft = {
      title: "Test Fest",
      description: "A festival",
      start_datetime: "2026-10-17T16:00",
      end_datetime: "2026-10-17T23:00",
      all_day: false,
      venue_name: "The Venue",
      address_line1: "1 Main St",
      state: "NC",
      zip: "27701",
      locality: ["durham"],
      categories: ["festival"],
      event_url: "",
      ticket_url: "",
      price: "",
      is_free: false,
      image_url: "",
      organizer_name: "",
      contact_email: "",
      contact_phone: "",
    };
    fetchMock.mockResolvedValue(jsonResponse({ event: eventPayload }));

    const result = await aiAutofill("CODE", "paste event text here");

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/ai-autofill`);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      access_code: "CODE",
      text: "paste event text here",
    });
    expect(result).toEqual({ event: eventPayload });
  });

  it("maps 400 (blank text) to an error", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ text: ["blank"] }, { ok: false, status: 400 }));

    await expect(aiAutofill("CODE", "")).rejects.toMatchObject({
      status: 400,
      message: expect.stringContaining("problem"),
    });
  });

  it("maps 403 (bad access code / rate limit) to the access-code message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 403 }));

    await expect(aiAutofill("BAD", "some text")).rejects.toMatchObject({
      status: 403,
      message: expect.stringContaining("Access code not recognized"),
    });
  });

  it("maps 502 (LLM down) to a generic failure message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 502 }));

    const err = await aiAutofill("CODE", "text").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
  });
});

describe("GET wrappers", () => {
  it("getJob sends the access code in the X-Broadcast-Access-Code header", async () => {
    const job = { job_id: "j1", status: "queued", targets: [] };
    fetchMock.mockResolvedValue(jsonResponse(job));

    await expect(getJob("CODE", "j1")).resolves.toEqual(job);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1`);
    expect(init.method).toBeUndefined();
    expect(init.headers).toEqual({ "X-Broadcast-Access-Code": "CODE" });
    expect(init.body).toBeUndefined();
  });

  it("getManualRecipe fetches the per-site recipe with the access header", async () => {
    const recipe = { site_key: "a", name: "A", url: "u", fields: [], captcha_hint: null, submit_selector: "#go" };
    fetchMock.mockResolvedValue(jsonResponse(recipe));

    await expect(getManualRecipe("CODE", "j1", "siteA")).resolves.toEqual(recipe);

    const [url, init] = lastCall(fetchMock);
    expect(url).toBe(`${BASE}/broadcast/jobs/j1/manual/siteA`);
    expect(init.headers).toEqual({ "X-Broadcast-Access-Code": "CODE" });
  });
});

describe("error mapping", () => {
  it("maps 403 to the access-code message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 403 }));

    await expect(previewBroadcast("BAD", EVENT)).rejects.toMatchObject({
      status: 403,
      message: expect.stringContaining("Access code not recognized"),
    });
  });

  it("maps 400 to a form-problem message echoing the body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ zip: ["required"] }, { ok: false, status: 400 }));

    await expect(previewBroadcast("CODE", EVENT)).rejects.toMatchObject({
      status: 400,
      message: expect.stringContaining("zip"),
    });
  });

  it("maps other failures to a generic message and throws ApiError", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));

    const error = await getJob("CODE", "j1").catch((e) => e);
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

    await openScreenshot("CODE", "/broadcast/jobs/j1/shot.png");

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

    await expect(openScreenshot("CODE", "/x.png")).rejects.toBeInstanceOf(ApiError);
  });
});
