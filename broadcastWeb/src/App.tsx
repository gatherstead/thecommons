import { useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker, { COMING_SOON } from "./components/SitePicker";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import { clearDraft, clearSession, loadDraft, loadSession, saveDraft, saveSession } from "./lib/persist";
import { sendFill, useExtension, WEB_STORE_URL } from "./hooks/useExtension";
import { AUTH_URL, authClient, fetchJwt, JWT_FRESH_MS } from "./lib/authClient";
import {
  type ApiAuth,
  aiAutofill,
  ApiError,
  cancelJob,
  directRecipe,
  directSubmit,
  getAccess,
  getJob,
  previewBroadcast,
  retryJob,
  retryStuck,
  submitReal,
  verifyCode,
} from "./services/broadcastApi";

const DEV_FIXTURE: EventDraft = {
  draft_id: "",
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

const EMPTY_DRAFT: EventDraft = {
  draft_id: "",
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

export const unfilledOptionalFields = (draft: EventDraft): string[] => {
  const missing: string[] = [];
  if (!draft.end_datetime || draft.end_datetime === "") missing.push("Ends");
  if (!draft.event_url || draft.event_url.trim() === "") missing.push("Event Page URL");
  if (!draft.ticket_url || draft.ticket_url.trim() === "") missing.push("Ticket URL");
  if (!draft.price || draft.price.trim() === "") missing.push("Price");
  if (!draft.image_url || draft.image_url.trim() === "") missing.push("Image URL");
  if (!draft.organizer_name || draft.organizer_name.trim() === "") missing.push("Contact Name");
  if (!draft.contact_email || draft.contact_email.trim() === "") missing.push("Contact Email");
  if (!draft.contact_phone || draft.contact_phone.trim() === "") missing.push("Contact Phone");
  return missing;
};

const POLL_MS = 3000;

// Self-heal thresholds — deliberately more aggressive than the backend's own
// 60s floor on started_at (see broadcast/routing.py); the server is the final
// word on whether a reset is actually safe.
const QUEUED_STUCK_MS = 30_000; // dispatch is near-instant now, so 30s is generous
const RUNNING_STUCK_MS = 90_000; // 3x BROADCAST_TIMEOUT_MS (30s default)
const MAX_AUTO_RETRIES_PER_SITE = 2;

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
  | "unavailable";

const restoreFillStatus = (
  saved: Record<string, string> | undefined
): Record<string, ExtFillStatus> => {
  const out: Record<string, ExtFillStatus> = {};
  for (const [key, value] of Object.entries(saved ?? {})) {
    out[key] = value === "submitted" || value === "unavailable"
      ? (value as ExtFillStatus)
      : "ready";
  }
  return out;
};

export default function App() {
  const session = authClient.useSession();
  // The minted JWT itself lives in a ref, not state — minting is now lazy
  // (see getJwt below) and happens outside React's render cycle, so there's
  // nothing for state to trigger a re-render over. `jwt` state still exists
  // for the handful of call sites that build ApiAuth synchronously (the
  // JobProgress prop, the poll snapshot) and just mirrors the ref's value.
  const jwtRef = useRef<string | null>(null);
  const jwtMintedAtRef = useRef<number>(0);
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

  const [draft, setDraft] = useState<EventDraft>({
    ...(DRAFT.draft ?? EMPTY_DRAFT),
    draft_id: DRAFT.draft?.draft_id || crypto.randomUUID(),
    ...STICKY_CONTACT,
  });
  const [preview, setPreview] = useState<PreviewResult | null>(DRAFT.preview ?? null);
  const [selected, setSelected] = useState<Set<string>>(new Set(DRAFT.selected ?? []));
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

  // Lazy JWT mint: returns the cached token if it's still fresh, else mints a
  // new one and caches it. Called right before an authed request fires (not
  // eagerly on every session change) so idle re-renders never hit the token
  // endpoint. `force` re-mints even if the cache looks fresh — used right
  // after sign-in when we need a token synchronously in hand for the first
  // getAccess call.
  const getJwt = async (force = false): Promise<string | null> => {
    const fresh = jwtRef.current && Date.now() - jwtMintedAtRef.current < JWT_FRESH_MS;
    if (fresh && !force) return jwtRef.current;
    const token = await fetchJwt();
    jwtRef.current = token;
    jwtMintedAtRef.current = Date.now();
    setJwt(token);
    return token;
  };

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

  // Access resolution is keyed on *identity*, not on session.data's object
  // identity — Better Auth hands back a new object on every refresh even
  // when the signed-in user hasn't changed, and each resolution used to cost
  // a getAccess round trip (a Neon read) plus a JWT mint. Re-resolve only
  // when the signed-in email, logged-out state, or the verified trial code
  // actually changes.
  const identity = `${session.data?.user?.email ?? ""}::${accessVerified ? verifiedCode : ""}`;
  const lastResolvedIdentityRef = useRef<string | null>(null);

  useEffect(() => {
    if (session.isPending) return;
    if (lastResolvedIdentityRef.current === identity) return;
    lastResolvedIdentityRef.current = identity;

    if (!session.data) {
      jwtRef.current = null;
      jwtMintedAtRef.current = 0;
      setJwt(null);
      setTier(0);
      setIsTrial(false);
      setUsesRemaining(null);
      setAccessSource(null);
      return;
    }
    getJwt(true).then(async (token) => {
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
      } catch {
        // account lookup failed — fall through to a previously verified code
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
    // Deliberately keyed on `identity` (a derived string), not session.data/
    // accessVerified/verifiedCode directly — those would restore per-render
    // re-resolution. The ref guard above is the actual dedupe; this dep array
    // just needs to re-run the effect when identity's value changes.
  }, [identity, session.isPending]);

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
    const id = setInterval(() => {
      const currentJobId = jobIdRef.current!;
      // Re-derive per tick (not captured once at effect-setup) so a poll that
      // outlives the JWT's freshness window picks up a re-minted token rather
      // than authenticating with a stale one.
      const authSnapPromise: Promise<ApiAuth> =
        accessSource === "code" && verifiedCode
          ? Promise.resolve({ accessCode: verifiedCode })
          : getJwt().then((token) => (token ? { jwt: token } : { accessCode: verifiedCode }));
      authSnapPromise.then((authSnap) => {
        getJob(authSnap, currentJobId)
          .then((fresh) => {
            setJob(fresh);
            detectAndHealStuck(authSnap, currentJobId, fresh);
          })
          .catch(() => {
            /* transient poll failure — keep polling */
          });
      });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [jobActive, verifiedCode, accessSource]);

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

  // One code box, two code kinds: the backend tries UPGRADE (permanent) first,
  // then TRIAL — either way it binds the code to this account (redeem_upgrade_code
  // / bind_trial_code), so a later getAccess({jwt}) restores it with no
  // re-entry, on any device. Nothing needs to be persisted client-side anymore.
  const handleVerifyCode = async () => {
    const trimmedCode = accessCode.trim();
    if (!trimmedCode || !session.data) return;
    const token = await getJwt();
    if (!token) return;
    setAccessError("");
    try {
      const result = await verifyCode({ jwt: token }, trimmedCode, draft.draft_id);
      setTier(result.tier);
      setIsTrial(result.is_trial);
      setUsesRemaining(result.uses_remaining);
      setAccessSource("jwt");
      setAccessVerified(false);
      setVerifiedCode("");
      setAccessCode("");
      setShowCodeEntry(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAccessError("Your session may have expired — sign in again.");
      } else {
        setAccessError(
          "Couldn't verify that code — check the code, or sign in again if your session expired.",
        );
      }
    }
  };

  const handleSignOut = async () => {
    await authClient.signOut();
    jwtRef.current = null;
    jwtMintedAtRef.current = 0;
    setJwt(null);
    setTier(0);
    setIsTrial(false);
    setUsesRemaining(null);
    setAccessSource(null);
    setAccessError("");

    resetCore();
    clearSession();

    setDraft((prev) => ({
      ...prev,
      organizer_name: "",
      contact_email: "",
      contact_phone: "",
    }));
  };

  const handleDraftChange = (next: EventDraft) => {
    setDraft(next);
    if (!job) {
      setPreview(null); // routing may change — stale previews mislead
      setError("");
    }
  };

  const handlePreview = async () => {
    setBusy(true);
    setError("");
    directSubmit(auth, draft.draft_id, toApiEvent(draft)).catch(() => {});
    try {
      const result = await previewBroadcast(auth, toApiEvent(draft));
      setPreview(result);
      // Coming-soon calendars are shown in the picker but can't be submitted —
      // keep them out of the default selection so they never enter the submit list.
      setSelected(
        new Set(
          result.eligible
            .map((s) => s.site_key)
            .filter((key) => !COMING_SOON.has(key))
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed.");
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
      setError(e instanceof Error ? e.message : "Retry failed.");
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
      setError(e instanceof Error ? e.message : "Submit failed.");
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
      setError(e instanceof Error ? e.message : "Cancel failed.");
    } finally {
      setBusy(false);
    }
  };

  const fillOne = async (siteKey: string) => {
    if (!extensionId) {
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unavailable" }));
      return;
    }
    setExtFillStatus((prev) => ({ ...prev, [siteKey]: "filling" }));
    try {
      const recipe = await directRecipe(auth, toApiEvent(draft), siteKey);
      const ok = await sendFill(extensionId, recipe);
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: ok ? "submitted" : "unavailable" }));
    } catch {
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unavailable" }));
    }
  };

  const resetCore = () => {
    clearDraft();
    jobIdRef.current = null;
    setJob(null);
    setPreview(null);
    setSelected(new Set());
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

  // Escape hatch for operators soft-locked by stale cache: clears every bit of
  // client state (draft, preview, job, statuses, access-code inputs, both
  // localStorage bundles) and signs the current user out. The server account
  // is never touched — the same user can sign back in right after.
  const handleResetSite = async () => {
    setAccessCode("");
    setAccessVerified(false);
    setVerifiedCode("");
    setAccessError("");
    setShowCodeEntry(false);
    setAccessSource(null);

    await handleSignOut();
  };

  const handleAiAutofill = async () => {
    setAiBusy(true);
    setError("");
    try {
      const result = await aiAutofill(auth, aiText);
      setDraft((prev) => ({
        ...EMPTY_DRAFT,
        organizer_name: prev.organizer_name,
        contact_email: prev.contact_email,
        contact_phone: prev.contact_phone,
        ...result.event,
        draft_id: crypto.randomUUID(),
      }));
      setPreview(null);
      setJob(null);
      setSelected(new Set());
      setAiText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI autofill failed.");
    } finally {
      setAiBusy(false);
    }
  };

  const draftValid =
    draft.title.trim() !== "" &&
    draft.description.trim() !== "" &&
    draft.start_datetime !== "" &&
    draft.venue_name.trim() !== "" &&
    draft.address_line1.trim() !== "" &&
    draft.zip.trim() !== "" &&
    draft.locality.length > 0 &&
    draft.categories.length > 0;

  const unfilled = unfilledOptionalFields(draft);
  const submittedCount = Object.values(extFillStatus).filter((s) => s === "submitted").length;
  const nameByKey: Record<string, string> = preview
    ? Object.fromEntries(preview.eligible.map((s) => [s.site_key, s.name]))
    : {};

  // Access flow: one step active at a time; done steps collapse to a summary
  // line, upcoming steps stay visible but dimmed so the path ahead is clear.
  const step2: "todo" | "active" | "done" = !signedIn ? "todo" : hasAccess ? "done" : "active";
  const step3: "todo" | "active" | "done" = !hasAccess ? "todo" : preview ? "done" : "active";
  const step4: "todo" | "active" = preview ? "active" : "todo";
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
          disabled={busy || job !== null || locked || !isDraftEmpty(draft)}
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
            onClick={() => { setDraft(DEV_FIXTURE); setPreview(null); setJob(null); setError(""); }}
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
                <button
                  type="button"
                  onClick={() => {
                    const portalUrl = `${AUTH_URL}/signin?redirect_to=${encodeURIComponent(window.location.href)}`;
                    window.location.href = portalUrl;
                  }}
                >
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
                  {isTrial ? (
                    usesRemaining !== null ? (
                      <>
                        Trial access — {usesRemaining} use{usesRemaining !== 1 ? "s" : ""} remaining.
                        One use per event previewed; edits are free.
                      </>
                    ) : (
                      <>
                        Trial access — this code is active for a limited time (about 3 days).
                        Preview and fill as many events as you like until it expires.
                      </>
                    )
                  ) : (
                    <>Tier {tier} access on this account.</>
                  )}{" "}
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => {
                      if (!showCodeEntry) resetForm();
                      setShowCodeEntry((v) => !v);
                    }}
                  >
                    Have another code?
                  </button>
                </p>
                {showCodeEntry && codeEntry}
              </>
            )}
          </li>

          {/* Step 3 — contact info */}
          <li className={stepClass(step3)}>
            <p className="step-label">Confirm your contact info</p>
            {step3 === "todo" && (
              <p className="hint">
                Name, email, and phone shown as the organizer contact on each calendar —
                prefilled from your account.
              </p>
            )}
            {step3 === "done" && (
              <p className="step-summary">
                {draft.organizer_name}
                {draft.contact_email ? ` · ${draft.contact_email}` : ""}
                {draft.contact_phone ? ` · ${draft.contact_phone}` : ""}
              </p>
            )}
            {step3 === "active" && (
              <div className="contact-row">
                <div className="field">
                  <label htmlFor="contact-name">Name</label>
                  <input
                    id="contact-name"
                    type="text"
                    value={draft.organizer_name ?? ""}
                    onChange={(e) => handleDraftChange({ ...draft, organizer_name: e.target.value })}
                    disabled={busy || job !== null || locked}
                    maxLength={200}
                  />
                </div>

                <div className="field">
                  <label htmlFor="contact-email">Email</label>
                  <input
                    id="contact-email"
                    type="email"
                    value={draft.contact_email ?? ""}
                    onChange={(e) => handleDraftChange({ ...draft, contact_email: e.target.value })}
                    disabled={busy || job !== null || locked}
                  />
                </div>

                <div className="field">
                  <label htmlFor="contact-phone">Phone</label>
                  <input
                    id="contact-phone"
                    type="tel"
                    value={draft.contact_phone ?? ""}
                    onChange={(e) => handleDraftChange({ ...draft, contact_phone: e.target.value })}
                    disabled={busy || job !== null || locked}
                    maxLength={40}
                  />
                </div>
              </div>
            )}
          </li>

          {/* Step 4 — autofill & submit */}
          <li className={stepClass(step4)}>
            <p className="step-label">Autofill &amp; submit your events</p>
            {step4 === "todo" ? (
              <p className="hint">
                Preview your event below to see which calendars it&rsquo;s eligible for.
              </p>
            ) : (
              <p className="step-summary">Scroll down to autofill and submit your events.</p>
            )}
            <p>
              <button
                type="button"
                className="reset-form-inline"
                onClick={handleResetSite}
                title="Clear all saved form/session data on this device and sign out — a hard reset of the whole site"
              >
                Hard Reset Site
              </button>
            </p>
          </li>
        </ol>
      </section>

      <section className="section">
        <h2>AI Autofill</h2>
        <div className={locked || tier < 2 ? "form-dim" : ""}>
          <p className="hint">
            Paste a raw event description, email, or flyer text below and the AI will fill
            the event fields for you.
            {tier < 2 && <em> Available with Tier 2 access.</em>}
          </p>
          <textarea
            className="ai-autofill-textarea"
            placeholder="Paste an event description / flyer text / email…"
            value={aiText}
            onChange={(e) => setAiText(e.target.value)}
            disabled={tier < 2 || !isDraftEmpty(draft) || aiBusy || job !== null || locked}
          />
          <div className="actions">
            <button
              type="button"
              onClick={handleAiAutofill}
              disabled={
                tier < 2 ||
                aiText.trim() === "" ||
                !isDraftEmpty(draft) ||
                aiBusy ||
                job !== null ||
                locked
              }
            >
              {aiBusy ? "Generating…" : "✨ Generate from text"}
            </button>
            {tier >= 2 && !isDraftEmpty(draft) && (
              <span className="section-note">
                AI autofill works on a blank event form — click Reset to clear the event
                details first.
              </span>
            )}
          </div>
        </div>
      </section>

      {/* ── The Event form ── */}
      <section className="section">
        <h2>The Event</h2>
        <div className={hasAccess && !locked ? "" : "form-dim"}>
          {!isDraftEmpty(draft) && (
            <p className="hint">Draft auto-saved on this device — cleared when you start over.</p>
          )}
          <EventForm draft={draft} onChange={handleDraftChange} disabled={busy || job !== null || locked || !hasAccess} />
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
                const isTerminal = status === "submitted" || status === "unavailable";
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
                    {status === "unavailable" && (
                      <span className="target-status unavailable">not available</span>
                    )}
                    {status !== "filling" && status !== "submitted" && status !== "unavailable" && (
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
                      if (next.has(key)) next.delete(key);
                      else next.add(key);
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
              Don't see a calendar you'd like?{" "}
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
