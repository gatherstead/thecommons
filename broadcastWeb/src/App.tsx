import { useCallback, useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker, { COMING_SOON } from "./components/SitePicker";
import { contactEmailError } from "./models/broadcastModels";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import {
  clearDraft,
  clearSession,
  clearStaleKeys,
  loadDraft,
  loadSession,
  saveDraft,
  saveSession,
} from "./lib/persist";
import { sendFillWithAck, useExtension, WEB_STORE_URL } from "./hooks/useExtension";
import { authClient, fetchJwt } from "./lib/authClient";
import {
  type ApiAuth,
  ApiError,
  aiAutofill,
  cancelJob,
  directRecipe,
  directSubmit,
  getAccess,
  getJob,
  previewBroadcast,
  redeemAccessCode,
  retryJob,
  retryStuck,
  SessionExpiredError,
  setTokenRefreshListener,
  submitReal,
} from "./services/broadcastApi";

const DEV_FIXTURE: Omit<EventDraft, "draft_id"> = {
  title: "Bull City BOOs Fest",
  description:
    "Join The MAKRS Society for our 5th annual Halloween Festival at Durham Central Park!\n\nCostumes Encouraged!!\n\nCool People. Cool Stuff.\n\n🍕 THE FOOD: 10-15 food trucks, breweries, cideries, wine, desserts and more!\n\n🔥 THE PERFORMANCES: Contortionist, magician, aerialist, fire performers and more!\n\n🎧 THE MUSIC: Live DJ keeping the party alive all night!\n\n🔮 THE EXPERIENCE: Lasers, fog, stilt walkers, tarot card readers, costume contests, selfie wall and more!\n\nVendor Applications: https://www.eventeny.com/events/vendor/?id=46443\nFood Truck Applications: https://www.eventeny.com/events/vendor/?id=46444\nEvent Website: https://makrs.com/bull-city-boos-fest",
  start_datetime: "2026-10-17T16:00",
  end_datetime: "2026-10-17T23:00",
  all_day: false,
  venue_name: "Durham Central Park",
  address_line1: "501 Foster St",
  state: "NC",
  zip: "27701",
  locality: ["durham"],
  categories: ["festival", "music", "food-drink", "nightlife", "community"],
  event_url: "https://makrs.com/bull-city-boos-fest",
  ticket_url: "",
  price: "",
  is_free: true,
  image_url: "",
  organizer_name: "The MAKRS Society",
  contact_email: "info@makrs.com",
  contact_phone: "",
};

const EMPTY_DRAFT: Omit<EventDraft, "draft_id"> = {
  title: "",
  description: "",
  start_datetime: "",
  end_datetime: "",
  all_day: false,
  venue_name: "",
  address_line1: "",
  state: "NC",
  zip: "",
  locality: [],
  categories: [],
  event_url: "",
  ticket_url: "",
  price: "",
  is_free: false,
  image_url: "",
  organizer_name: "",
  contact_email: "",
  contact_phone: "",
};

// The AI-autofill response carries every EventDraft key, with unknowns as
// "" / [] / false. Strip those (and draft_id, which the form owns) so the
// result can be merged over the current draft without erasing fields the
// model simply didn't mention. Consequence, deliberate: autofill can set a
// field but never clear one — clearing stays a manual edit.
export const meaningfulFields = (event: EventDraft): Partial<EventDraft> => {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(event)) {
    if (key === "draft_id") continue;
    if (typeof value === "string" && value.trim() === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    if (value === false || value === null || value === undefined) continue;
    out[key] = value;
  }
  return out as Partial<EventDraft>;
};

export const isDraftEmpty = (draft: EventDraft): boolean =>
  draft.title.trim() === "" &&
  draft.description.trim() === "" &&
  draft.start_datetime === "" &&
  (draft.end_datetime === undefined || draft.end_datetime === "") &&
  !draft.all_day &&
  draft.venue_name.trim() === "" &&
  draft.address_line1.trim() === "" &&
  (draft.state === "" || draft.state === "NC") &&
  draft.zip.trim() === "" &&
  draft.locality.length === 0 &&
  draft.categories.length === 0 &&
  (draft.event_url === undefined || draft.event_url.trim() === "") &&
  (draft.ticket_url === undefined || draft.ticket_url.trim() === "") &&
  (draft.price === undefined || draft.price.trim() === "") &&
  !draft.is_free &&
  (draft.image_url === undefined || draft.image_url.trim() === "");

// Organizer/contact fields are required (see EventForm's contact fields and
// draftValid) so they're excluded here — this list is for genuinely optional
// fields only.
export const unfilledOptionalFields = (draft: EventDraft): string[] => {
  const missing: string[] = [];
  if (!draft.end_datetime || draft.end_datetime === "") missing.push("Ends");
  if (!draft.event_url || draft.event_url.trim() === "") missing.push("Event Page URL");
  if (!draft.ticket_url || draft.ticket_url.trim() === "") missing.push("Ticket URL");
  if (!draft.price || draft.price.trim() === "") missing.push("Price");
  if (!draft.image_url || draft.image_url.trim() === "") missing.push("Event image");
  return missing;
};

const POLL_MS = 3000;
// Poll backoff: widen the delay when a tick brings no change, so an idle tab
// (job stuck, or nothing left to check) lets Neon's DB spin down instead of
// getting pinged every 3s forever. Any change resets to POLL_MS.
const POLL_BACKOFF_FACTOR = 1.5;
const POLL_MAX_MS = 30_000;
// Stop polling a single job after this long — a job that's still "active"
// after 6 hours is not going to resolve itself; surface a neutral affordance
// instead of polling Neon indefinitely.
const POLL_HARD_CAP_MS = 6 * 60 * 60 * 1000;

// Self-heal thresholds — deliberately more aggressive than the backend's own
// 60s floor on started_at (see broadcast/routing.py); the server is the final
// word on whether a reset is actually safe.
const QUEUED_STUCK_MS = 30_000; // dispatch is near-instant now, so 30s is generous
const RUNNING_STUCK_MS = 90_000; // 3x BROADCAST_TIMEOUT_MS (30s default)
const MAX_AUTO_RETRIES_PER_SITE = 2;

// Cheap fingerprint of "did anything worth re-rendering-for change" — job
// status plus each target's status, in order. Used to decide whether the
// next poll tick should back off or reset to the base cadence.
const jobFingerprint = (job: JobDetail): string =>
  `${job.status}|${job.targets.map((t) => t.status).join(",")}`;

clearStaleKeys();
const SESSION = loadSession();
const DRAFT = loadDraft();

const STICKY_CONTACT = {
  organizer_name: SESSION.organizer_name ?? "",
  contact_email: SESSION.contact_email ?? "",
  contact_phone: SESSION.contact_phone ?? "",
};

// datetime-local gives a naive local string; send an unambiguous instant.
const toApiEvent = (draft: EventDraft): EventDraft => ({
  ...draft,
  start_datetime: draft.start_datetime
    ? new Date(draft.start_datetime).toISOString()
    : "",
  end_datetime: draft.end_datetime
    ? new Date(draft.end_datetime).toISOString()
    : undefined,
});

type ExtFillStatus =
  | "idle"
  | "sending"
  | "sent"
  | "error"
  | "ready"
  | "filling"
  | "submitted"
  // The extension itself never dispatched the fill (both the ack path and
  // its one-shot fallback failed) — most commonly a build so old it
  // predates even {type:"fill"} runtime.onMessageExternal. Distinct from
  // "not-installed" (no extension at all) so the copy can point at
  // *updating* rather than installing (see the README's fill-ack >= 0.4.1
  // note).
  | "unavailable"
  // No extension id resolved at all (useExtension's ping never found one) —
  // distinct from "unavailable" so the copy is install-oriented rather than
  // update-oriented; these are different user actions.
  | "not-installed"
  // content.js's completion ack came back with ok:false (a field handler or
  // runFill itself threw) — a real, confirmed failure, distinct from
  // "unavailable" (the extension/tab never opened at all).
  | "failed"
  // The /broadcast/direct-recipe call itself failed (403 rate-limit, expired
  // session, 404 adapter, network error) — the extension was never even
  // reached. Kept separate from "failed" (a confirmed content.js failure) and
  // "unavailable"/"not-installed" (extension-side problems) so the message
  // points at the actual cause instead of blaming the extension.
  | "recipe-failed"
  // No completion ack arrived within FILL_ACK_TIMEOUT_MS — NOT the same as
  // FILLED and not the same as a confirmed failure either: the fill may well
  // have gone through, we just never heard back (ticket 48.2).
  | "unconfirmed";

// Statuses that are done-for-now and worth remembering across a reload —
// mirrors the terminal set the render below treats as resubmit-eligible.
const TERMINAL_FILL_STATUSES = new Set<ExtFillStatus>([
  "submitted",
  "unavailable",
  "not-installed",
  "failed",
  "recipe-failed",
  "unconfirmed",
]);

const restoreFillStatus = (
  saved: Record<string, string> | undefined
): Record<string, ExtFillStatus> => {
  const out: Record<string, ExtFillStatus> = {};
  for (const [key, value] of Object.entries(saved ?? {})) {
    out[key] = TERMINAL_FILL_STATUSES.has(value as ExtFillStatus)
      ? (value as ExtFillStatus)
      : "ready";
  }
  return out;
};

export default function App() {
  const session = authClient.useSession();
  const [jwt, setJwt] = useState<string | null>(null);
  const [tier, setTier] = useState<0 | 1 | 2>(0);
  const [isTrial, setIsTrial] = useState(false);
  const [usesRemaining, setUsesRemaining] = useState<number | null>(null);

  const [accessCode, setAccessCode] = useState(SESSION.accessCode ?? "");
  const [accessVerified, setAccessVerified] = useState(SESSION.verified ?? false);
  // The code that actually passed verification — the input box is scratch space
  // until Verify succeeds, so API auth never picks up a half-typed code.
  const [verifiedCode, setVerifiedCode] = useState(
    SESSION.verified ? SESSION.accessCode ?? "" : ""
  );
  // Which credential granted the current tier: a permanent account tier (jwt)
  // or a per-request trial code (code). Decides which auth header API calls use.
  const [accessSource, setAccessSource] = useState<"jwt" | "code" | null>(null);
  const [accessError, setAccessError] = useState("");
  const [showCodeEntry, setShowCodeEntry] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const [draft, setDraft] = useState<EventDraft>({
    ...(DRAFT.draft ?? EMPTY_DRAFT),
    draft_id: DRAFT.draft?.draft_id || crypto.randomUUID(),
    ...STICKY_CONTACT,
  });
  const [preview, setPreview] = useState<PreviewResult | null>(DRAFT.preview ?? null);
  const [selected, setSelected] = useState<Set<string>>(new Set(DRAFT.selected ?? []));
  // Destinations the user explicitly unchecked in the picker — survives a
  // re-preview (48.7) so editing a field and re-previewing doesn't silently
  // re-add a calendar the user deliberately excluded. Cleared on a fresh event.
  const [deselected, setDeselected] = useState<Set<string>>(new Set());
  const [job, setJob] = useState<JobDetail | null>(DRAFT.job ?? null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiText, setAiText] = useState("");
  const [error, setError] = useState("");
  const [extFillStatus, setExtFillStatus] = useState<Record<string, ExtFillStatus>>(
    restoreFillStatus(DRAFT.extFillStatus)
  );
  const [speedSubmit, setSpeedSubmit] = useState(DRAFT.speedSubmit ?? false);
  const jobIdRef = useRef<string | null>(DRAFT.jobId ?? null);
  // Poll cadence state: current delay (backs off on unchanged ticks, resets
  // to POLL_MS on any change), the fingerprint from the previous successful
  // poll, and when the current job first became active (for the 6h hard cap).
  const pollDelayRef = useRef(POLL_MS);
  const lastFingerprintRef = useRef<string | null>(null);
  const firstActiveAtRef = useRef<Map<string, number>>(new Map());
  const [pollTimedOut, setPollTimedOut] = useState(false);
  // De-dupes the access-resolution effect: only re-run fetchJwt+getAccess when
  // the signed-in identity actually changes, not on every session.data reference churn.
  const resolvedIdentityRef = useRef<string | null | undefined>(undefined);
  // Auto-retry counters per site_key, capped at MAX_AUTO_RETRIES_PER_SITE.
  // A ref (not state) so bumping it doesn't re-trigger the poll effect, and
  // survives re-renders across ticks of the same interval.
  const autoRetryCountRef = useRef<Map<string, number>>(new Map());
  // Site keys with an auto-retry currently in flight — guards against firing
  // a second retryStuck for the same target before the first one's response
  // (and the next getJob poll) has had a chance to move it out of "stuck".
  const autoRetryInFlightRef = useRef<Set<string>>(new Set());
  // Site keys that have exhausted the auto-retry cap and are still stuck —
  // surfaced to JobProgress for the "Failed - Worker Stuck" label.
  const [exhaustedStuckKeys, setExhaustedStuckKeys] = useState<Set<string>>(new Set());
  const { installed: extInstalled, extensionId, recheck: recheckExt } = useExtension();

  // A trial code authenticates per-request via header; a permanent account
  // tier authenticates via JWT. Whichever granted the tier wins.
  const auth: ApiAuth =
    accessSource === "code" && verifiedCode
      ? { accessCode: verifiedCode }
      : jwt
        ? { jwt }
        : { accessCode: verifiedCode };

  const jobActive = job !== null && (job.status === "queued" || job.status === "running");
  const locked = Boolean(preview);
  const signedIn = Boolean(session.data);
  // Access always requires a login; a verified trial code alone is not enough.
  const hasAccess = signedIn && tier >= 1;

  // broadcastApi transparently remints an expired JWT on a 401/403; keep our
  // copy in step so the next request doesn't repeat the refresh round-trip.
  useEffect(() => {
    setTokenRefreshListener(setJwt);
    return () => setTokenRefreshListener(null);
  }, []);

  // A SessionExpiredError means the Better Auth session itself is gone, so a
  // retry can never succeed — drop the local auth state and send the user back
  // to sign-in rather than surfacing a raw backend string.
  const describeError = useCallback((e: unknown, fallback: string): string => {
    if (e instanceof SessionExpiredError) {
      setJwt(null);
      setTier(0);
      setIsTrial(false);
      setUsesRemaining(null);
      setAccessSource(null);
      return "Your session expired — please sign in again.";
    }
    return e instanceof Error ? e.message : fallback;
  }, []);

  useEffect(() => {
    if (session.isPending) return;
    const identity = session.data?.user?.email ?? null;
    if (resolvedIdentityRef.current === identity) return;
    resolvedIdentityRef.current = identity;

    if (!session.data) {
      setJwt(null);
      setTier(0);
      setIsTrial(false);
      setUsesRemaining(null);
      setAccessSource(null);
      return;
    }
    fetchJwt().then(async (token) => {
      setJwt(token);
      if (!token) return;
      try {
        const access = await getAccess({ jwt: token });
        if (access.tier > 0) {
          setTier(access.tier);
          setIsTrial(access.is_trial);
          setUsesRemaining(access.uses_remaining);
          setAccessSource("jwt");
          return;
        }
        // Tier 0 on a logged-in account is a legitimate "enter your access
        // code" state, not an error — fall through without setting accessError.
      } catch (e) {
        if (e instanceof ApiError && e.status === 403) {
          setAccessError("We couldn't verify your session — please sign out and sign in again.");
        }
        // other errors — fall through to a previously verified code
      }
      // No permanent tier on the account — re-validate a persisted trial code.
      if (accessVerified && verifiedCode) {
        try {
          const access = await getAccess({ accessCode: verifiedCode });
          setTier(access.tier);
          setIsTrial(access.is_trial);
          setUsesRemaining(access.uses_remaining);
          setAccessSource("code");
          return;
        } catch {
          setAccessVerified(false);
          setVerifiedCode("");
        }
      }
      setTier(0);
      setIsTrial(false);
      setUsesRemaining(null);
      setAccessSource(null);
    });
  }, [session.data, session.isPending]);

  // Prefill the contact fields from the account once access unlocks —
  // only fills blanks, never overwrites what the user typed.
  useEffect(() => {
    const user = session.data?.user;
    if (!hasAccess || !user) return;
    setDraft((prev) => ({
      ...prev,
      organizer_name: prev.organizer_name || user.name || "",
      contact_email: prev.contact_email || user.email || "",
    }));
  }, [hasAccess, session.data]);

  useEffect(() => {
    saveSession({
      accessCode: accessVerified && verifiedCode ? verifiedCode : accessCode,
      verified: accessVerified,
      organizer_name: draft.organizer_name,
      contact_email: draft.contact_email,
      contact_phone: draft.contact_phone,
    });
  }, [accessCode, accessVerified, verifiedCode, draft.organizer_name, draft.contact_email, draft.contact_phone]);

  useEffect(() => {
    saveDraft({
      draft, preview, selected: [...selected], job, jobId: jobIdRef.current,
      extFillStatus, speedSubmit,
    });
  }, [draft, preview, selected, job, extFillStatus, speedSubmit]);

  // A fresh job_id means a fresh run — the retry cap and in-flight guard are
  // per-job, so start them clean rather than carrying over counts from a
  // previous submission that happened to reuse a stale ref.
  useEffect(() => {
    autoRetryCountRef.current = new Map();
    autoRetryInFlightRef.current = new Set();
    setExhaustedStuckKeys(new Set());
  }, [job?.job_id]);

  useEffect(() => {
    if (!jobActive || !jobIdRef.current) return;
    const authSnap: ApiAuth =
      accessSource === "code" && verifiedCode
        ? { accessCode: verifiedCode }
        : jwt
          ? { jwt }
          : { accessCode: verifiedCode };

    const currentJobId = jobIdRef.current;
    if (!firstActiveAtRef.current.has(currentJobId)) {
      firstActiveAtRef.current.set(currentJobId, Date.now());
    }
    pollDelayRef.current = POLL_MS;
    // Seed from the job already in state so the very first tick can detect
    // "unchanged" and widen immediately, instead of always resetting once.
    lastFingerprintRef.current = job ? jobFingerprint(job) : null;

    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      // Pause while the tab is hidden — resumes via the visibilitychange
      // listener below rather than firing requests into a backgrounded tab.
      if (document.hidden) return;

      const firstActiveAt = firstActiveAtRef.current.get(currentJobId);
      if (firstActiveAt !== undefined && Date.now() - firstActiveAt > POLL_HARD_CAP_MS) {
        setPollTimedOut(true);
        return;
      }

      getJob(authSnap, currentJobId)
        .then((fresh) => {
          if (cancelled) return;
          setJob(fresh);
          detectAndHealStuck(authSnap, currentJobId, fresh);
          const fingerprint = jobFingerprint(fresh);
          if (lastFingerprintRef.current !== null && lastFingerprintRef.current === fingerprint) {
            pollDelayRef.current = Math.min(pollDelayRef.current * POLL_BACKOFF_FACTOR, POLL_MAX_MS);
          } else {
            pollDelayRef.current = POLL_MS;
          }
          lastFingerprintRef.current = fingerprint;
        })
        .catch(() => {
          /* transient poll failure — keep polling at the current cadence */
        })
        .finally(() => {
          if (!cancelled) schedule();
        });
    };

    const schedule = () => {
      timeoutId = setTimeout(tick, pollDelayRef.current);
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        if (timeoutId !== null) clearTimeout(timeoutId);
        timeoutId = null;
      } else if (timeoutId === null) {
        // Tab became visible again — poll right away, then resume the schedule.
        tick();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    if (!document.hidden) schedule();

    return () => {
      cancelled = true;
      if (timeoutId !== null) clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [jobActive, verifiedCode, jwt, accessSource]);

  // New job (or job cleared) — the hard-cap timer and timed-out flag are
  // per-job, so start clean rather than carrying over from a prior submission.
  useEffect(() => {
    setPollTimedOut(false);
  }, [job?.job_id]);

  // Stuck-target self-heal: with server-side polling gone, this client loop is
  // the primary detector. A job stuck "queued" too long (dispatch should be
  // near-instant) or a target stuck "in_progress" too long (worker likely
  // died mid-run) gets one retryStuck call per tick it's newly detected,
  // capped at MAX_AUTO_RETRIES_PER_SITE per site_key so a permanently broken
  // site can't loop forever.
  const detectAndHealStuck = (authSnap: ApiAuth, jobId: string, fresh: JobDetail) => {
    if (fresh.status !== "queued" && fresh.status !== "running") return;

    const now = Date.now();
    const stuckKeys: string[] = [];

    if (fresh.status === "queued") {
      const createdAge = now - new Date(fresh.created_at).getTime();
      if (createdAge > QUEUED_STUCK_MS) {
        for (const t of fresh.targets) {
          if (t.status === "pending") stuckKeys.push(t.site_key);
        }
      }
    }

    for (const t of fresh.targets) {
      if (t.status !== "in_progress" || !t.started_at) continue;
      const runningAge = now - new Date(t.started_at).getTime();
      if (runningAge > RUNNING_STUCK_MS) stuckKeys.push(t.site_key);
    }

    const toRetry = stuckKeys.filter((key) => {
      if (autoRetryInFlightRef.current.has(key)) return false; // already firing
      const count = autoRetryCountRef.current.get(key) ?? 0;
      if (count >= MAX_AUTO_RETRIES_PER_SITE) {
        setExhaustedStuckKeys((prev) => (prev.has(key) ? prev : new Set(prev).add(key)));
        return false;
      }
      return true;
    });
    if (toRetry.length === 0) return;

    toRetry.forEach((key) => {
      autoRetryInFlightRef.current.add(key);
      autoRetryCountRef.current.set(key, (autoRetryCountRef.current.get(key) ?? 0) + 1);
    });
    retryStuck(authSnap, jobId, toRetry)
      .then(() => getJob(authSnap, jobId).then(setJob))
      .catch(() => {
        /* transient failure — the next poll tick will re-detect and retry */
      })
      .finally(() => {
        toRetry.forEach((key) => autoRetryInFlightRef.current.delete(key));
      });
  };

  // One code box, two code kinds: try it as an UPGRADE code first (permanent,
  // bound to the account), and if the backend rejects that, as a TRIAL code
  // (per-request header auth). Either way the user sees a single Verify step.
  const handleVerifyCode = async () => {
    // Trim once, up front: codes arrive by copy/paste and a stray trailing
    // space made a valid code hash to something else entirely, surfacing as
    // an unexplainable "Access code not recognized."
    const code = accessCode.trim();
    if (!code || !jwt) return;
    setAccessError("");
    try {
      const result = await redeemAccessCode({ jwt }, code);
      setTier(result.tier);
      setIsTrial(false);
      setUsesRemaining(null);
      setAccessSource("jwt");
      setAccessVerified(false);
      setAccessCode("");
      setShowCodeEntry(false);
      return;
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 403)) {
        setAccessError("Could not verify the access code. Try again.");
        return;
      }
    }
    try {
      const access = await getAccess({ accessCode: code });
      if (access.tier === 0) {
        throw new ApiError(403, "Access code not recognized. Check the code and try again.");
      }
      setAccessVerified(true);
      setVerifiedCode(code);
      setAccessSource("code");
      setTier(access.tier);
      setIsTrial(access.is_trial);
      setUsesRemaining(access.uses_remaining);
      setShowCodeEntry(false);
    } catch (e) {
      setAccessVerified(false);
      // Surface the backend's specific message (expired/exhausted → contact
      // support) when present; fall back to a generic not-recognized message.
      setAccessError(
        e instanceof ApiError && e.status === 403 && e.message
          ? e.message
          : "Access code not recognized. Check the code and try again.",
      );
    }
  };

  // Full navigation to the shared auth portal — the cross-subdomain session
  // brings the user back to this exact URL automatically after sign-in.
  const handleSignIn = () => {
    const authUrl = import.meta.env.VITE_BETTER_AUTH_URL || "http://localhost:3000";
    window.location.href = `${authUrl}/signin?redirect_to=${encodeURIComponent(window.location.href)}`;
  };

  // Signing out wipes the form entirely — clear both persistence scopes and
  // reload for a guaranteed-clean, stale-data-free mount (same approach as
  // handleHardReset). try/finally so the reload still fires if signOut rejects.
  const handleSignOut = async () => {
    clearDraft();
    clearSession();
    try {
      await authClient.signOut();
    } finally {
      window.location.reload();
    }
  };

  // Full hard reset: clears local persistence and the auth session, then
  // reloads for a guaranteed-clean mount rather than manually resetting every
  // field. try/finally so the reload still fires even if signOut rejects.
  const handleHardReset = async () => {
    clearDraft();
    clearSession();
    try {
      await authClient.signOut();
    } finally {
      window.location.reload();
    }
  };

  // Functional-updater contract (48.3): the child hands us a `prev => next`
  // function instead of a materialized draft, so we always merge against
  // React's current state rather than whatever the child closed over — the
  // fix for the stale-closure race where an in-flight image upload's `await`
  // resolved with an old `draft` snapshot and reverted intervening edits.
  const handleDraftChange = (updater: (prev: EventDraft) => EventDraft) => {
    setDraft(updater);
    if (!job) {
      setPreview(null); // routing may change — stale previews mislead
      setError("");
    }
  };

  const handlePreview = async () => {
    setBusy(true);
    setError("");
    directSubmit(auth, draft.draft_id, toApiEvent(draft)).catch((e) => {
      console.error("[direct-submit] fire-and-forget call failed:", e);
    });
    try {
      const result = await previewBroadcast(auth, toApiEvent(draft));
      setPreview(result);
      // Coming-soon calendars are shown in the picker but can't be submitted —
      // keep them out of the default selection so they never enter the submit list.
      // Newly-eligible destinations default to selected, but a destination the
      // user explicitly unchecked earlier (tracked in `deselected`) stays
      // unchecked across this re-preview (48.7) rather than silently reviving.
      // Prune deselected keys that are no longer eligible at all, so the set
      // doesn't grow stale forever.
      const eligibleKeys = new Set(result.eligible.map((s) => s.site_key));
      const stillDeselected = new Set([...deselected].filter((key) => eligibleKeys.has(key)));
      setDeselected(stillDeselected);
      setSelected(
        new Set(
          result.eligible
            .map((s) => s.site_key)
            .filter((key) => !COMING_SOON.has(key) && !stillDeselected.has(key))
        )
      );
    } catch (e) {
      setError(describeError(e, "Preview failed."));
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async (siteKeys: string[]) => {
    if (!jobIdRef.current) return;
    setBusy(true);
    setError("");
    try {
      await retryJob(auth, jobIdRef.current, siteKeys);
      setJob(await getJob(auth, jobIdRef.current));
    } catch (e) {
      setError(describeError(e, "Retry failed."));
    } finally {
      setBusy(false);
    }
  };

  const handleSubmitReal = async (siteKeys: string[]) => {
    if (!jobIdRef.current) return;
    setError("");
    try {
      await submitReal(auth, jobIdRef.current, siteKeys);
      setJob(await getJob(auth, jobIdRef.current));
    } catch (e) {
      setError(describeError(e, "Submit failed."));
    }
  };

  const handleCancel = async () => {
    if (!jobIdRef.current) return;
    setBusy(true);
    setError("");
    try {
      await cancelJob(auth, jobIdRef.current);
      setJob(await getJob(auth, jobIdRef.current));
    } catch (e) {
      setError(describeError(e, "Cancel failed."));
    } finally {
      setBusy(false);
    }
  };

  const fillOne = async (siteKey: string) => {
    if (!extensionId) {
      // No extension resolved at all — distinct from "unavailable" (a
      // dispatch failure against a real, resolved extension) so the copy can
      // point at installing rather than updating.
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "not-installed" }));
      return;
    }
    setExtFillStatus((prev) => ({ ...prev, [siteKey]: "filling" }));
    try {
      const recipe = await directRecipe(auth, toApiEvent(draft), siteKey);
      // FILLED is only ever reported once content.js's own completion ack
      // says so — never inferred from the tab having opened (the bug this
      // ticket fixes). "timeout" and "dispatch-failed" are deliberately
      // different outcomes: the former means we just never heard back (or
      // the one-shot fallback opened the tab with no ack channel at all),
      // the latter means the fill never started even after the fallback.
      const result = await sendFillWithAck(extensionId, recipe);
      if (result.kind === "complete") {
        setExtFillStatus((prev) => ({
          ...prev,
          [siteKey]: result.summary.ok ? "submitted" : "failed",
        }));
      } else if (result.kind === "timeout") {
        setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unconfirmed" }));
      } else {
        setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unavailable" }));
      }
    } catch (e) {
      // Only a confirmed extension-side failure earns "not available"/
      // "failed". A failed /broadcast/direct-recipe call (403 rate-limit,
      // expired session, 404 adapter) never reaches the extension at all —
      // reporting it as an extension problem sends people to
      // reinstall/update a working extension while the real error stays
      // invisible in the network tab. "recipe-failed" keeps it distinct.
      setError(describeError(e, "Couldn't build the fill for this site."));
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "recipe-failed" }));
    }
  };

  const resetCore = () => {
    clearDraft();
    jobIdRef.current = null;
    setJob(null);
    setPreview(null);
    setSelected(new Set());
    setDeselected(new Set());
    setDraft((prev) => ({
      ...EMPTY_DRAFT,
      draft_id: crypto.randomUUID(),
      organizer_name: prev.organizer_name,
      contact_email: prev.contact_email,
      contact_phone: prev.contact_phone,
    }));
    setError("");
    setAiText("");
    setExtFillStatus({});
    setSpeedSubmit(false);
    autoRetryCountRef.current = new Map();
    autoRetryInFlightRef.current = new Set();
    setExhaustedStuckKeys(new Set());
  };

  // Reset everything for a fresh event, but keep the (verified) access/auth state.
  const startOver = resetCore;

  const resetForm = resetCore;

  const handleAiAutofill = async () => {
    setAiBusy(true);
    setError("");
    try {
      const result = await aiAutofill(auth, aiText);
      // Merge, never replace. The backend always returns every EventDraft key
      // (unknowns as "" / [] / false), so spreading the response wholesale
      // wiped every field the model didn't happen to re-extract — which made
      // "change the phone number to X" erase the rest of the form. Only
      // non-empty values overwrite what's already there, so a targeted edit
      // touches exactly the fields it names and a first paste still fills
      // everything. draft_id is preserved: it keys trial metering, and a fresh
      // one per autofill would burn a use on every edit.
      setDraft((prev) => ({ ...prev, ...meaningfulFields(result.event) }));
      setPreview(null);
      setJob(null);
      setSelected(new Set());
      setDeselected(new Set());
      setAiText("");
    } catch (e) {
      setError(describeError(e, "AI autofill failed."));
    } finally {
      setAiBusy(false);
    }
  };

  const contactEmailErr = contactEmailError(draft.contact_email);

  const draftValid =
    draft.title.trim() !== "" &&
    draft.description.trim() !== "" &&
    draft.start_datetime !== "" &&
    draft.venue_name.trim() !== "" &&
    draft.address_line1.trim() !== "" &&
    draft.zip.trim() !== "" &&
    draft.locality.length > 0 &&
    draft.categories.length > 0 &&
    (draft.organizer_name ?? "").trim() !== "" &&
    (draft.contact_email ?? "").trim() !== "" &&
    contactEmailErr === "" &&
    (draft.contact_phone ?? "").trim() !== "";

  const unfilled = unfilledOptionalFields(draft);
  const submittedCount = Object.values(extFillStatus).filter((s) => s === "submitted").length;
  const nameByKey: Record<string, string> = preview
    ? Object.fromEntries(preview.eligible.map((s) => [s.site_key, s.name]))
    : {};

  // Access flow: one step active at a time; done steps collapse to a summary
  // line, upcoming steps stay visible but dimmed so the path ahead is clear.
  const step2: "todo" | "active" | "done" = !signedIn ? "todo" : hasAccess ? "done" : "active";
  // Step 3 (organizer/contact info) lives in the main event form now (48.10) —
  // this step just points down to it.
  const step3: "todo" | "active" = preview ? "active" : "todo";
  const stepClass = (state: "todo" | "active" | "done") => `access-step access-step-${state}`;

  const codeEntry = (
    <>
      <div className="verify-row">
        <input
          id="access-code"
          type="password"
          value={accessCode}
          onChange={(e) => {
            setAccessCode(e.target.value);
            setAccessError("");
          }}
          autoComplete="off"
          disabled={busy || job !== null || locked}
          placeholder="Provided by The Commons"
          aria-label="Access code"
        />
        <button
          type="button"
          className="verify"
          onClick={handleVerifyCode}
          disabled={accessCode.trim() === ""}
        >
          Verify
        </button>
      </div>
      {accessError && <p className="field-error">{accessError}</p>}
    </>
  );

  return (
    <div className="page">
      <header className="masthead">
        {import.meta.env.DEV && (
          <button
            type="button"
            className="dev-autofill"
            onClick={() => {
              setDraft(() => ({ ...DEV_FIXTURE, draft_id: crypto.randomUUID() }));
              setPreview(null);
              setJob(null);
              setError("");
            }}
            title="Autofill with Bull City BOOs Fest test data"
          >
            ⚡ Dev autofill
          </button>
        )}
        <h1>BROADCAST SYNDICATE</h1>
        <p className="tagline">One event in — many local calendars out.</p>
        <div className="rule-double" />
      </header>

      <section className="section">
        <h2>Access</h2>
        <ol className="access-steps">
          {/* Step 1 — sign in */}
          <li className={stepClass(signedIn ? "done" : "active")}>
            <p className="step-label">Sign in</p>
            {session.isPending ? (
              <p className="hint">Checking session…</p>
            ) : signedIn ? (
              <p className="step-summary">
                {session.data!.user.email}{" "}
                <button type="button" className="linklike" onClick={handleSignOut}>
                  Sign out
                </button>
              </p>
            ) : (
              <>
                <p className="hint">Use your account, or create one in a few seconds.</p>
                <button type="button" onClick={handleSignIn}>
                  Sign in / Create account
                </button>
              </>
            )}
          </li>

          {/* Step 2 — access code */}
          <li className={stepClass(step2)}>
            <p className="step-label">Enter your access code</p>
            {step2 === "todo" && (
              <p className="hint">The Commons team gives you a code — we verify it on the spot.</p>
            )}
            {step2 === "active" && (
              <>
                <p className="hint">
                  This account has no broadcast access yet — enter the code from The
                  Commons team and we&rsquo;ll verify it on the spot.
                </p>
                {codeEntry}
              </>
            )}
            {step2 === "done" && (
              <>
                <p className="step-summary">
                  {accessSource === "code" && isTrial && usesRemaining !== null ? (
                    <>
                      Trial access — {usesRemaining} use{usesRemaining !== 1 ? "s" : ""} remaining.
                      One use per event previewed; edits are free.
                    </>
                  ) : (
                    <>Tier {tier} access on this account.</>
                  )}{" "}
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => setShowCodeEntry((v) => !v)}
                  >
                    Have another code?
                  </button>
                </p>
                {showCodeEntry && codeEntry}
              </>
            )}
          </li>

          {/* Step 3 — autofill & submit */}
          <li className={stepClass(step3)}>
            <p className="step-label">Autofill &amp; submit your events</p>
            {step3 === "todo" ? (
              <p className="hint">
                Fill in the event below (including organizer/contact info) and preview it
                to see which calendars it&rsquo;s eligible for.
              </p>
            ) : (
              <p className="step-summary">Scroll down to autofill and submit your events.</p>
            )}
          </li>
        </ol>
        <div className="actions">
          {confirmReset ? (
            <button type="button" className="danger" onClick={handleHardReset}>
              Click again to confirm — this logs you out and clears everything
            </button>
          ) : (
            <button
              type="button"
              className="linklike"
              onClick={() => setConfirmReset(true)}
            >
              Reset everything
            </button>
          )}
        </div>
      </section>

      <section className="section">
        <h2>AI Autofill</h2>
        <div className={locked || tier < 2 ? "form-dim" : ""}>
          <p className="hint">
            Paste a raw event description, email, or flyer text below and the AI will fill
            the event fields for you.
            {tier === 0 && <em> Available with Tier 2 access.</em>}
          </p>
          {tier === 1 && (
            <p className="field-error">
              Talk to support and upgrade your plan to access this feature.
            </p>
          )}
          {locked && (
            <p className="section-note">
              Locked while you&rsquo;re reviewing this event — click &ldquo;Make changes&rdquo;
              below to edit it again.
            </p>
          )}
          {tier >= 2 && !isDraftEmpty(draft) && (
            <p className="section-note">
              Generating will replace the event details below.
            </p>
          )}
          <textarea
            className="ai-autofill-textarea"
            placeholder="Paste an event description / flyer text / email…"
            value={aiText}
            onChange={(e) => setAiText(e.target.value)}
            disabled={tier < 2 || aiBusy || job !== null || locked}
          />
          <div className="actions">
            <button
              type="button"
              onClick={handleAiAutofill}
              disabled={tier < 2 || aiText.trim() === "" || aiBusy || job !== null || locked}
            >
              {aiBusy ? "Generating…" : "✨ Generate from text"}
            </button>
          </div>
        </div>
      </section>

      {/* ── The Event form ── */}
      <section className="section">
        <div className="section-title-row">
          <h2>The Event</h2>
          <button
            type="button"
            className="reset-form-inline"
            onClick={resetForm}
            disabled={busy || aiBusy || job !== null || !hasAccess || locked}
            title="Clear the form and start over"
          >
            Reset form
          </button>
        </div>
        <div className={hasAccess && !locked ? "" : "form-dim"}>
          {!isDraftEmpty(draft) && (
            <p className="hint">Draft auto-saved on this device — cleared when you start over.</p>
          )}
          {locked && (
            <p className="section-note">
              Locked while you&rsquo;re reviewing this event — click &ldquo;Make changes&rdquo;
              below to edit any field.
            </p>
          )}
          <EventForm
            draft={draft}
            onChange={handleDraftChange}
            disabled={busy || job !== null || locked || !hasAccess}
            auth={auth}
          />
        </div>
        <div className="actions">
          {preview ? (
            <>
              <button
                type="button"
                onClick={() => { setPreview(null); setSelected(new Set()); setExtFillStatus({}); setSpeedSubmit(false); }}
              >
                Make changes
              </button>
              <button type="button" onClick={resetForm}>
                Reset form
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={handlePreview}
                disabled={busy || job !== null || !draftValid || !hasAccess}
              >
                {busy ? "Checking…" : "Preview Destinations"}
              </button>
              {!hasAccess && (
                <span className="section-note">
                  Complete the Access steps above to unlock the form — this is a preview
                  of what you&rsquo;ll fill in.
                </span>
              )}
              {hasAccess && !draftValid && (
                <span className="section-note">Fill the required (*) fields to preview.</span>
              )}
            </>
          )}
        </div>
      </section>

      {preview && !job && (
        <section className="section">
          <h2>Destinations</h2>

          {!speedSubmit && unfilled.length > 0 && (
            <p className="optional-unfilled">
              <em>Not provided: {unfilled.join(", ")}</em>
            </p>
          )}

          {speedSubmit ? (
            <ul className="site-list">
              {[...selected].map((siteKey) => {
                const siteName = nameByKey[siteKey] ?? siteKey;
                const status = extFillStatus[siteKey] ?? "ready";
                const isTerminal = TERMINAL_FILL_STATUSES.has(status);
                const isFilling = status === "filling";
                return (
                  <li key={siteKey}>
                    <button
                      type="button"
                      className="linklike site-name"
                      onClick={() => fillOne(siteKey)}
                      disabled={isTerminal || isFilling}
                    >
                      {siteName}
                    </button>
                    {status === "filling" && (
                      <span className="target-status pending">opening…</span>
                    )}
                    {status === "submitted" && (
                      <span className="target-status submitted">filled</span>
                    )}
                    {status === "not-installed" && (
                      <span className="target-status unavailable">
                        extension not installed —{" "}
                        <a href={WEB_STORE_URL} target="_blank" rel="noopener noreferrer">
                          install it
                        </a>
                      </span>
                    )}
                    {status === "unavailable" && (
                      <span className="target-status unavailable">
                        extension didn&rsquo;t respond — update it to the latest version
                      </span>
                    )}
                    {status === "recipe-failed" && (
                      <span className="target-status failed">
                        couldn&rsquo;t build this fill — try again
                      </span>
                    )}
                    {status === "failed" && (
                      <span className="target-status failed">fill failed</span>
                    )}
                    {status === "unconfirmed" && (
                      <span className="target-status unconfirmed">
                        couldn&rsquo;t confirm — check the tab
                      </span>
                    )}
                    {status !== "filling" &&
                      status !== "submitted" &&
                      status !== "unavailable" &&
                      status !== "not-installed" &&
                      status !== "failed" &&
                      status !== "recipe-failed" &&
                      status !== "unconfirmed" && (
                        <span className="target-status ready">ready</span>
                      )}
                    {isTerminal && (
                      <button
                        type="button"
                        className="resubmit-icon"
                        onClick={() => fillOne(siteKey)}
                        title="Re-open and re-fill this calendar"
                        aria-label={`Resubmit ${siteName}`}
                      >
                        ↻
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <>
              {!extInstalled && (
                <div className="ext-download">
                  <a
                    href={WEB_STORE_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={recheckExt}
                    className="dark btn"
                  >
                    Download the extension
                  </a>
                  <p className="section-note">
                    Needed to autofill the forms so you don't have to. Free, two click install.
                  </p>
                </div>
              )}

              <div className={!extInstalled ? "greyed-out" : undefined}>
                <SitePicker
                  preview={preview}
                  selected={selected}
                  onToggle={(key) =>
                    setSelected((prev) => {
                      const next = new Set(prev);
                      if (next.has(key)) {
                        next.delete(key);
                        // Record the manual uncheck so a later re-preview
                        // (edit a field → Preview again) doesn't silently
                        // re-add this destination (48.7).
                        setDeselected((prevDeselected) => new Set(prevDeselected).add(key));
                      } else {
                        next.add(key);
                        setDeselected((prevDeselected) => {
                          if (!prevDeselected.has(key)) return prevDeselected;
                          const nextDeselected = new Set(prevDeselected);
                          nextDeselected.delete(key);
                          return nextDeselected;
                        });
                      }
                      return next;
                    })
                  }
                  disabled={busy || !extInstalled}
                />
              </div>

              {extInstalled && (
                <div className="actions">
                  <button
                    type="button"
                    className="dark"
                    onClick={() => {
                      setSpeedSubmit(true);
                      setExtFillStatus(
                        Object.fromEntries(
                          [...selected].map((k): [string, ExtFillStatus] => [k, "ready"])
                        )
                      );
                    }}
                    disabled={busy || selected.size === 0}
                  >
                    Populate Forms!
                  </button>
                </div>
              )}
            </>
          )}
          {submittedCount > 0 && (
            <p className="time-saved">You've saved {submittedCount * 10} minutes today!</p>
          )}
          {extInstalled && (
            <p className="section-note calendar-request">
              Don't see a calendar you expect?{" "}
              <a
                href="https://docs.google.com/forms/d/e/1FAIpQLSfCZeSLpDLnKwZt-dFDnfRfdIvFUlEoYPE_OMRdPQnxpyGxlA/viewform?usp=dialog"
                target="_blank"
                rel="noopener noreferrer"
              >
                Request it here
              </a>
              .
            </p>
          )}
        </section>
      )}

      {job && (
        <section className="section">
          <h2>Progress</h2>
          {pollTimedOut && (
            <p className="section-note">
              Still working after a while — refresh the page to check the latest status.
            </p>
          )}
          <JobProgress
            job={job}
            auth={auth}
            onRetry={handleRetry}
            onSubmitReal={handleSubmitReal}
            retrying={busy}
            stuckExhausted={exhaustedStuckKeys}
          />
          {jobActive && (
            <div className="actions">
              <button type="button" className="danger" onClick={handleCancel} disabled={busy}>
                {busy ? "Stopping…" : "Stop all jobs"}
              </button>
            </div>
          )}
        </section>
      )}

      {error && (
        <section className="section">
          <p className="error-text">{error}</p>
        </section>
      )}

      {(job || preview) && extInstalled && (
        <section className="section">
          <div className="actions">
            <button type="button" className="dark" onClick={startOver}>
              Reset &amp; submit another event
            </button>
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSfCZeSLpDLnKwZt-dFDnfRfdIvFUlEoYPE_OMRdPQnxpyGxlA/viewform?usp=dialog"
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
            >
              Give feedback
            </a>
          </div>
        </section>
      )}

      <footer className="footer-rule rule-thick">
        Submissions are placed by hand-built scripts, one site at a time. Sites
        that require a login or human check are flagged for manual follow-up —
        never bypassed.
      </footer>
    </div>
  );
}
