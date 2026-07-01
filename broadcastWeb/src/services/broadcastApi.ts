// Mirrors the house service pattern (theCommonsWeb/src/services/eventService.ts):
// plain fetch per call, response.ok checks, no shared client wrapper.
// The access code is passed per request and never stored.

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

const messageFor = (status: number, body: unknown): string => {
  if (status === 403) return "Access code not recognized (or rate limit reached — wait a minute).";
  if (status === 400) return `The form has a problem: ${JSON.stringify(body)}`;
  return `Request failed (${status}).`;
};

async function post<T>(path: string, payload: object): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`POST ${path} failed:`, response.status, body);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as T;
}

export const previewBroadcast = (
  accessCode: string,
  event: EventDraft,
): Promise<PreviewResult> =>
  post<PreviewResult>("/broadcast/preview", { access_code: accessCode, event });

export const submitBroadcast = (
  accessCode: string,
  event: EventDraft,
  siteKeys: string[],
  dryRun: boolean,
): Promise<{ job_id: string }> =>
  post<{ job_id: string }>("/broadcast/submit", {
    access_code: accessCode,
    event,
    site_keys: siteKeys,
    dry_run: dryRun,
  });

export const getJob = async (
  accessCode: string,
  jobId: string,
): Promise<JobDetail> => {
  const response = await fetch(`${API_BASE}/broadcast/jobs/${jobId}`, {
    headers: { "X-Broadcast-Access-Code": accessCode },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`GET job ${jobId} failed:`, response.status);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as JobDetail;
};

export const retryJob = (
  accessCode: string,
  jobId: string,
  siteKeys: string[],
): Promise<{ job_id: string; requeued: number }> =>
  post(`/broadcast/jobs/${jobId}/retry`, {
    access_code: accessCode,
    site_keys: siteKeys,
  });

// Promote dry-run targets to a real submission within an existing job. The
// backend flips dry_run=false and re-queues only the sites still in dry run.
export const submitReal = (
  accessCode: string,
  jobId: string,
  siteKeys: string[],
): Promise<{ job_id: string; submitted: number }> =>
  post(`/broadcast/jobs/${jobId}/submit-real`, {
    access_code: accessCode,
    site_keys: siteKeys,
  });

export const aiAutofill = (
  accessCode: string,
  text: string,
): Promise<{ event: EventDraft }> =>
  post<{ event: EventDraft }>("/broadcast/ai-autofill", {
    access_code: accessCode,
    text,
  });

// Stop a job: the backend skips pending targets and marks it canceled so the
// worker won't pick up the remaining sites.
export const cancelJob = (
  accessCode: string,
  jobId: string,
): Promise<{ job_id: string; status: string; skipped: number }> =>
  post(`/broadcast/jobs/${jobId}/cancel`, { access_code: accessCode });

export const directRecipe = (
  accessCode: string,
  event: EventDraft,
  siteKey: string,
): Promise<Recipe> =>
  post<Recipe>("/broadcast/direct-recipe", {
    access_code: accessCode,
    event,
    site_key: siteKey,
  });

export const getManualRecipe = async (
  accessCode: string,
  jobId: string,
  siteKey: string,
): Promise<Recipe> => {
  const response = await fetch(
    `${API_BASE}/broadcast/jobs/${jobId}/manual/${siteKey}`,
    { headers: { "X-Broadcast-Access-Code": accessCode } },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`GET manual recipe ${siteKey} failed:`, response.status);
    throw new ApiError(response.status, messageFor(response.status, body));
  }
  return body as Recipe;
};

// Screenshots are operator-gated behind the access-code header, so a plain
// <a href> cannot fetch them — pull the bytes and open a blob URL instead.
export const openScreenshot = async (
  accessCode: string,
  screenshotPath: string,
): Promise<void> => {
  const response = await fetch(`${API_BASE}${screenshotPath}`, {
    headers: { "X-Broadcast-Access-Code": accessCode },
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
