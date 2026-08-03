// Mirrors the house service pattern (theCommonsWeb/src/services/eventService.ts):
// plain fetch per call, response.ok checks, no shared client wrapper.
// Auth is passed per request via ApiAuth (Bearer JWT wins over access-code header).
//
// The SPA mints its JWT once on mount and holds it in memory for the whole
// session (see App.tsx), so it eventually expires mid-session — the backend
// then returns 401/403 (backendServer/broadcast/access.py deliberately does
// NOT fall through to the access-code path for a present-but-invalid JWT).
// authFetch() below transparently remints the token and retries once, so an
// expired token never surfaces as a user-visible error.

import { fetchJwt } from "../lib/authClient";
import type { EventDraft, JobDetail, PreviewResult, Recipe } from "../models/broadcastModels";

const RAW_BASE =
  import.meta.env.VITE_BROADCAST_API_BASE_URL || "http://127.0.0.1:8000";

// A value like "https:api.thecommons.town" (missing "//") passes `new URL()`
// on its own — the WHATWG parser silently inserts the "//" when there's no
// base URL. But fetch() always resolves against the page's origin as a base,
// and in that mode the same string is treated as *relative*, silently
// resolving API calls against the SPA's own origin instead of the API host.
// Require the "//" explicitly so a typo fails loudly instead of both "working"
// in a one-off check and misrouting in fetch().
if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(RAW_BASE)) {
  throw new Error(
    `VITE_BROADCAST_API_BASE_URL is not a valid absolute URL: "${RAW_BASE}". ` +
      `Check broadcastWeb/.env — a missing "//" silently resolves relative to the SPA's own origin.`,
  );
}
new URL(RAW_BASE); // still throws on genuinely malformed values (spaces, no scheme, etc.)
const API_BASE = RAW_BASE;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Distinguishable from ApiError so callers can branch on it (e.g. prompt the
// user to sign in again) instead of rendering a raw backend error string.
// Thrown only when a JWT-authenticated request fails auth and the follow-up
// fetchJwt() also comes back empty — i.e. the Better Auth session itself is
// gone, not just the in-memory token.
export class SessionExpiredError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again.");
    this.name = "SessionExpiredError";
  }
}

// Bearer JWT wins over the access-code header; neither = no auth header.
export type ApiAuth = { jwt?: string; accessCode?: string };

export function authHeaders(auth: ApiAuth): Record<string, string> {
  if (auth.jwt) return { Authorization: `Bearer ${auth.jwt}` };
  if (auth.accessCode) return { "X-Broadcast-Access-Code": auth.accessCode };
  return {};
}

// App.tsx mints the JWT once on mount and holds it in state; when authFetch
// remints a token behind the scenes, this lets App.tsx learn about it so the
// *next* request doesn't immediately have to repeat the refresh dance. Purely
// an optional hook — nothing here depends on it being registered.
type TokenRefreshListener = (jwt: string) => void;
let tokenRefreshListener: TokenRefreshListener | null = null;
export function setTokenRefreshListener(listener: TokenRefreshListener | null): void {
  tokenRefreshListener = listener;
}

// Single-flight: concurrent requests that all 401/403 together share one
// in-flight fetchJwt() call instead of each minting their own token.
let inFlightRefresh: Promise<string | null> | null = null;
function refreshJwt(): Promise<string | null> {
  if (!inFlightRefresh) {
    inFlightRefresh = fetchJwt().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

// Wraps every authenticated fetch. On a 401/403 for a JWT-bearing request,
// remints the token once and retries the same request; any other outcome
// (access-code auth, non-auth-error status) passes through untouched. Retried
// at most once — a failure on the retry is surfaced as-is by the caller.
//
// A 403 is ambiguous: the backend uses it both for a stale/invalid JWT (a
// refresh fixes this) and for a legitimate business denial like an expired
// access code (no refresh will ever fix this, and its `detail` message is
// the whole point — see backendServer/broadcast/views.py:369-381). The
// response body can't be trusted to tell those apart, but the token can:
//   - refresh comes back with a DIFFERENT token → the token really was
//     stale → retry once with the new token.
//   - refresh comes back with the SAME token we just sent → the token was
//     never the problem → leave the original response's error (status +
//     backend detail) to surface as-is instead of masking it.
//   - refresh comes back null → the Better Auth session itself is gone.
//     For a 401 that's unambiguous (401 never carries business meaning on
//     this backend — grep confirms it's never emitted), so it's reported as
//     a session problem. A 403 is inherently ambiguous, though, and a failed
//     refresh doesn't tell us *why* it failed — it never proves the 403 was
//     a token issue, so the original response (with whatever business
//     detail it carries) is left to surface rather than guessing.
async function authFetch(url: string, init: RequestInit, auth: ApiAuth): Promise<Response> {
  const response = await fetch(url, init);
  if ((response.status !== 401 && response.status !== 403) || !auth.jwt) {
    return response;
  }
  const sentJwt = auth.jwt;
  const newJwt = await refreshJwt();
  if (newJwt === null) {
    if (response.status === 401) {
      throw new SessionExpiredError();
    }
    return response;
  }
  if (newJwt === sentJwt) {
    return response;
  }
  tokenRefreshListener?.(newJwt);
  return fetch(url, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), Authorization: `Bearer ${newJwt}` },
  });
}

const messageFor = (status: number, body: unknown): string => {
  // Prefer the backend's own `detail` (e.g. an expired/exhausted access code)
  // so the specific message reaches the user instead of a generic 403 string.
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (status === 403) {
    return typeof detail === "string"
      ? detail
      : "Access denied — check your credentials or access code.";
  }
  if (status === 400) return `The form has a problem: ${JSON.stringify(body)}`;
  return `Request failed (${status}).`;
};

async function post<T>(path: string, auth: ApiAuth, payload: object): Promise<T> {
  const response = await authFetch(
    `${API_BASE}${path}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(auth) },
      body: JSON.stringify(payload),
    },
    auth,
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`POST ${path} failed:`, response.status, body);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as T;
}

export const getAccess = async (
  auth: ApiAuth,
): Promise<{ tier: 0 | 1 | 2; is_trial: boolean; uses_remaining: number | null }> => {
  const response = await authFetch(`${API_BASE}/broadcast/access`, { headers: authHeaders(auth) }, auth);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error("GET /broadcast/access failed:", response.status, body);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as { tier: 0 | 1 | 2; is_trial: boolean; uses_remaining: number | null };
};

// Requires auth.jwt — upgrade codes are only redeemable while logged in.
export const redeemAccessCode = (
  auth: ApiAuth,
  accessCode: string,
): Promise<{ tier: 0 | 1 | 2 }> =>
  post<{ tier: 0 | 1 | 2 }>("/broadcast/redeem", auth, { access_code: accessCode });

export const previewBroadcast = (
  auth: ApiAuth,
  event: EventDraft,
): Promise<PreviewResult> =>
  post<PreviewResult>("/broadcast/preview", auth, { draft_id: event.draft_id, event });

export const submitBroadcast = (
  auth: ApiAuth,
  event: EventDraft,
  siteKeys: string[],
  dryRun: boolean,
): Promise<{ job_id: string }> =>
  post<{ job_id: string }>("/broadcast/submit", auth, {
    event,
    site_keys: siteKeys,
    dry_run: dryRun,
  });

export const getJob = async (
  auth: ApiAuth,
  jobId: string,
): Promise<JobDetail> => {
  const response = await authFetch(
    `${API_BASE}/broadcast/jobs/${jobId}`,
    { headers: authHeaders(auth) },
    auth,
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`GET job ${jobId} failed:`, response.status);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as JobDetail;
};

export const retryJob = (
  auth: ApiAuth,
  jobId: string,
  siteKeys: string[],
): Promise<{ job_id: string; requeued: number }> =>
  post(`/broadcast/jobs/${jobId}/retry`, auth, {
    site_keys: siteKeys,
  });

// Self-heal path for a stuck queued/in_progress target — unlike retryJob, the
// backend will reset an in_progress target back to pending (subject to its own
// 60s floor on started_at) so a hung worker doesn't block the site forever.
export const retryStuck = (
  auth: ApiAuth,
  jobId: string,
  siteKeys: string[],
): Promise<{ job_id: string; requeued: number }> =>
  post(`/broadcast/jobs/${jobId}/retry-stuck`, auth, {
    site_keys: siteKeys,
  });

// Promote dry-run targets to a real submission within an existing job. The
// backend flips dry_run=false and re-queues only the sites still in dry run.
export const submitReal = (
  auth: ApiAuth,
  jobId: string,
  siteKeys: string[],
): Promise<{ job_id: string; submitted: number }> =>
  post(`/broadcast/jobs/${jobId}/submit-real`, auth, {
    site_keys: siteKeys,
  });

// Multipart upload — file field name must be "image" to match the backend
// serializer. Unlike post(), there's no JSON Content-Type header: the
// browser sets the multipart boundary itself when given a FormData body.
export const uploadImage = async (
  auth: ApiAuth,
  file: File,
): Promise<{ url: string }> => {
  const formData = new FormData();
  formData.append("image", file);
  const response = await authFetch(
    `${API_BASE}/broadcast/upload-image`,
    { method: "POST", headers: authHeaders(auth), body: formData },
    auth,
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error("POST /broadcast/upload-image failed:", response.status, body);
    // Unlike the JSON-body endpoints, upload-image always fails with a
    // human-readable {"detail": "..."} written for a non-technical operator
    // (bad file type, too large, dimensions too big) — render it verbatim
    // rather than routing it through messageFor()'s generic 400 handling.
    const detail = (body as { detail?: unknown } | null)?.detail;
    const message = typeof detail === "string" ? detail : messageFor(response.status, body);
    throw new ApiError(response.status, message);
  }
  return body as { url: string };
};

export const aiAutofill = (
  auth: ApiAuth,
  text: string,
): Promise<{ event: EventDraft }> =>
  post<{ event: EventDraft }>("/broadcast/ai-autofill", auth, { text });

// Stop a job: the backend skips pending targets and marks it canceled so the
// worker won't pick up the remaining sites.
export const cancelJob = (
  auth: ApiAuth,
  jobId: string,
): Promise<{ job_id: string; status: string; skipped: number }> =>
  post(`/broadcast/jobs/${jobId}/cancel`, auth, {});

export const directSubmit = (
  auth: ApiAuth,
  draftId: string,
  event: EventDraft,
): Promise<{ status: string; draft_id: string }> =>
  post<{ status: string; draft_id: string }>("/api/events/direct-submit", auth, {
    draft_id: draftId,
    event,
  });

export const directRecipe = (
  auth: ApiAuth,
  event: EventDraft,
  siteKey: string,
): Promise<Recipe> =>
  post<Recipe>("/broadcast/direct-recipe", auth, {
    event,
    site_key: siteKey,
  });

export const getManualRecipe = async (
  auth: ApiAuth,
  jobId: string,
  siteKey: string,
): Promise<Recipe> => {
  const response = await authFetch(
    `${API_BASE}/broadcast/jobs/${jobId}/manual/${siteKey}`,
    { headers: authHeaders(auth) },
    auth,
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`GET manual recipe ${siteKey} failed:`, response.status);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as Recipe;
};

// Screenshots are operator-gated behind the auth header, so a plain
// <a href> cannot fetch them — pull the bytes and open a blob URL instead.
export const openScreenshot = async (
  auth: ApiAuth,
  screenshotPath: string,
): Promise<void> => {
  const response = await authFetch(
    `${API_BASE}${screenshotPath}`,
    { headers: authHeaders(auth) },
    auth,
  );
  if (!response.ok) {
    console.error("screenshot fetch failed:", response.status);
    throw new ApiError(response.status, "Could not load the screenshot.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
};
