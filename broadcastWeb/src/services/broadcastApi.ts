// Mirrors the house service pattern (theCommonsWeb/src/services/eventService.ts):
// plain fetch per call, response.ok checks, no shared client wrapper.
// Auth is passed per request via ApiAuth (Bearer JWT wins over access-code header).

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

// Bearer JWT wins over the access-code header; neither = no auth header.
export type ApiAuth = { jwt?: string; accessCode?: string };

export function authHeaders(auth: ApiAuth): Record<string, string> {
  if (auth.jwt) return { Authorization: `Bearer ${auth.jwt}` };
  if (auth.accessCode) return { "X-Broadcast-Access-Code": auth.accessCode };
  return {};
}

const messageFor = (status: number, body: unknown): string => {
  if (status === 403) return "Access denied — check your credentials or access code.";
  if (status === 400) return `The form has a problem: ${JSON.stringify(body)}`;
  return `Request failed (${status}).`;
};

async function post<T>(path: string, auth: ApiAuth, payload: object): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(auth) },
    body: JSON.stringify(payload),
  });
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
  const response = await fetch(`${API_BASE}/broadcast/access`, {
    headers: authHeaders(auth),
  });
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
  const response = await fetch(`${API_BASE}/broadcast/jobs/${jobId}`, {
    headers: authHeaders(auth),
  });
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
  const response = await fetch(
    `${API_BASE}/broadcast/jobs/${jobId}/manual/${siteKey}`,
    { headers: authHeaders(auth) },
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
  const response = await fetch(`${API_BASE}${screenshotPath}`, {
    headers: authHeaders(auth),
  });
  if (!response.ok) {
    console.error("screenshot fetch failed:", response.status);
    throw new ApiError(response.status, "Could not load the screenshot.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
};
