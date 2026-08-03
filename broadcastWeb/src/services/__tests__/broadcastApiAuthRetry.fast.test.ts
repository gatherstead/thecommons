import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EventDraft } from "../../models/broadcastModels";

// vi.hoisted ensures this mock fn reference is available inside the vi.mock
// factory below (which is hoisted above regular imports).
const { fetchJwtMock } = vi.hoisted(() => ({
  fetchJwtMock: vi.fn(async (): Promise<string | null> => null),
}));

vi.mock("../../lib/authClient", () => ({
  fetchJwt: fetchJwtMock,
}));

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

const jsonResponse = (
  body: unknown,
  { ok = true, status = 200 }: { ok?: boolean; status?: number } = {},
) => ({ ok, status, json: () => Promise.resolve(body) });

const authHeader = (mock: ReturnType<typeof vi.fn>, callIndex: number): string | undefined => {
  const [, init] = mock.mock.calls[callIndex] as [string, RequestInit];
  return (init.headers as Record<string, string>)["Authorization"];
};

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchJwtMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("authFetch retry-on-401/403", () => {
  it("transparently refreshes an expired JWT and retries the request once", async () => {
    const { previewBroadcast } = await import("../broadcastApi");
    const result = { eligible: [{ site_key: "a", name: "A" }], excluded: [] };

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "invalid token" }, { ok: false, status: 403 }))
      .mockResolvedValueOnce(jsonResponse(result));
    fetchJwtMock.mockResolvedValueOnce("fresh.jwt.token");

    await expect(previewBroadcast({ jwt: "stale.jwt.token" }, EVENT)).resolves.toEqual(result);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchJwtMock).toHaveBeenCalledTimes(1);
    expect(authHeader(fetchMock, 0)).toBe("Bearer stale.jwt.token");
    expect(authHeader(fetchMock, 1)).toBe("Bearer fresh.jwt.token");
  });

  it("does not retry more than once when the reminted token is also rejected", async () => {
    const { previewBroadcast } = await import("../broadcastApi");

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "invalid token" }, { ok: false, status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ detail: "still invalid" }, { ok: false, status: 401 }));
    fetchJwtMock.mockResolvedValueOnce("fresh.jwt.token");

    await expect(previewBroadcast({ jwt: "stale.jwt.token" }, EVENT)).rejects.toMatchObject({
      status: 401,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchJwtMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces a SessionExpiredError (not a raw ApiError) when the session itself is dead", async () => {
    const { previewBroadcast, SessionExpiredError, ApiError } = await import("../broadcastApi");

    // 401 is unambiguous (this backend never uses it for a business denial —
    // only 403 is overloaded that way), so a failed refresh on a 401 is
    // reported as a session problem.
    fetchMock.mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 401 }));
    fetchJwtMock.mockResolvedValueOnce(null);

    const error = await previewBroadcast({ jwt: "stale.jwt.token" }, EVENT).catch((e) => e);

    expect(error).toBeInstanceOf(SessionExpiredError);
    expect(error).not.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry and preserves the original ApiError when a 403's refresh returns the SAME token", async () => {
    const { previewBroadcast, ApiError } = await import("../broadcastApi");

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { detail: "This access code has expired — please contact support." },
        { ok: false, status: 403 },
      ),
    );
    fetchJwtMock.mockResolvedValueOnce("stale.jwt.token");

    const error = await previewBroadcast({ jwt: "stale.jwt.token" }, EVENT).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      message: "This access code has expired — please contact support.",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchJwtMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry and preserves the original ApiError when a 403's refresh itself fails (null)", async () => {
    const { previewBroadcast, ApiError, SessionExpiredError } = await import("../broadcastApi");

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { detail: "This access code has expired — please contact support." },
        { ok: false, status: 403 },
      ),
    );
    fetchJwtMock.mockResolvedValueOnce(null);

    const error = await previewBroadcast({ jwt: "stale.jwt.token" }, EVENT).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).not.toBeInstanceOf(SessionExpiredError);
    expect(error).toMatchObject({
      status: 403,
      message: "This access code has expired — please contact support.",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not attempt a refresh for access-code auth (no JWT to expire)", async () => {
    const { previewBroadcast } = await import("../broadcastApi");

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "bad code" }, { ok: false, status: 403 }));

    await expect(previewBroadcast({ accessCode: "CODE" }, EVENT)).rejects.toMatchObject({
      status: 403,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchJwtMock).not.toHaveBeenCalled();
  });

  it("calls the registered token-refresh listener with the reminted JWT", async () => {
    const { previewBroadcast, setTokenRefreshListener } = await import("../broadcastApi");
    const listener = vi.fn();
    setTokenRefreshListener(listener);

    fetchMock
      .mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ eligible: [], excluded: [] }));
    fetchJwtMock.mockResolvedValueOnce("fresh.jwt.token");

    await previewBroadcast({ jwt: "stale.jwt.token" }, EVENT);

    expect(listener).toHaveBeenCalledWith("fresh.jwt.token");
    setTokenRefreshListener(null);
  });

  it("single-flight: concurrent 401s share exactly one refresh call", async () => {
    const { previewBroadcast, getJob } = await import("../broadcastApi");

    let resolveRefresh!: (token: string) => void;
    fetchJwtMock.mockImplementationOnce(
      () => new Promise<string | null>((resolve) => (resolveRefresh = resolve)),
    );

    // Every call in this test 401s until the reminted token shows up in the
    // Authorization header, so each of the three concurrent requests below
    // resolves on its own retry rather than needing per-call mock sequencing.
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      const authz = (init?.headers as Record<string, string> | undefined)?.["Authorization"];
      if (authz === "Bearer fresh.jwt.token") {
        return Promise.resolve(jsonResponse({ eligible: [], excluded: [] }));
      }
      return Promise.resolve(jsonResponse({}, { ok: false, status: 401 }));
    });

    const auth = { jwt: "stale.jwt.token" };
    const p1 = previewBroadcast(auth, EVENT);
    const p2 = previewBroadcast(auth, EVENT);
    const p3 = getJob(auth, "job-1");

    // Let all three requests make their initial (401'd) fetch and call into
    // refreshJwt() before the in-flight refresh resolves.
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    resolveRefresh("fresh.jwt.token");

    await expect(Promise.all([p1, p2, p3])).resolves.toBeDefined();
    expect(fetchJwtMock).toHaveBeenCalledTimes(1);
  });
});
