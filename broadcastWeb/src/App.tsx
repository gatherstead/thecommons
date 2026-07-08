import { useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker, { COMING_SOON } from "./components/SitePicker";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import { clearDraft, loadDraft, loadSession, saveDraft, saveSession } from "./lib/persist";
import { sendFill, useExtension, WEB_STORE_URL } from "./hooks/useExtension";
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
  retryJob,
  submitReal,
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
  const [jwt, setJwt] = useState<string | null>(null);
  const [tier, setTier] = useState<0 | 1 | 2>(0);
  const [isTrial, setIsTrial] = useState(false);
  const [usesRemaining, setUsesRemaining] = useState<number | null>(null);

  const [accessCode, setAccessCode] = useState(SESSION.accessCode ?? "");
  const [accessVerified, setAccessVerified] = useState(SESSION.verified ?? false);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginName, setLoginName] = useState("");
  const [loginMode, setLoginMode] = useState<"signin" | "signup">("signin");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

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
  const { installed: extInstalled, extensionId, recheck: recheckExt } = useExtension();

  const auth: ApiAuth = jwt ? { jwt } : { accessCode };

  const jobActive = job !== null && (job.status === "queued" || job.status === "running");
  const locked = Boolean(preview);
  const hasAccess = tier >= 1;

  useEffect(() => {
    if (session.data) {
      fetchJwt().then(async (token) => {
        setJwt(token);
        if (token) {
          try {
            const access = await getAccess({ jwt: token });
            setTier(access.tier);
            setIsTrial(access.is_trial);
            setUsesRemaining(access.uses_remaining);
          } catch {
            setTier(0);
            setIsTrial(false);
            setUsesRemaining(null);
          }
        }
      });
    } else if (!session.isPending) {
      setJwt(null);
      if (!accessVerified) {
        setTier(0);
        setIsTrial(false);
        setUsesRemaining(null);
      }
    }
  }, [session.data, session.isPending]);

  // On mount: re-validate a persisted access code so tier info is current.
  useEffect(() => {
    if (accessVerified && !session.data) {
      getAccess({ accessCode }).then((access) => {
        setTier(access.tier);
        setIsTrial(access.is_trial);
        setUsesRemaining(access.uses_remaining);
      }).catch(() => {
        setAccessVerified(false);
        setTier(0);
      });
    }
  }, []); // mount only — intentional

  useEffect(() => {
    saveSession({
      accessCode,
      verified: accessVerified,
      organizer_name: draft.organizer_name,
      contact_email: draft.contact_email,
      contact_phone: draft.contact_phone,
    });
  }, [accessCode, accessVerified, draft.organizer_name, draft.contact_email, draft.contact_phone]);

  useEffect(() => {
    saveDraft({
      draft, preview, selected: [...selected], job, jobId: jobIdRef.current,
      extFillStatus, speedSubmit,
    });
  }, [draft, preview, selected, job, extFillStatus, speedSubmit]);

  useEffect(() => {
    if (!jobActive || !jobIdRef.current) return;
    const authSnap: ApiAuth = jwt ? { jwt } : { accessCode };
    const id = setInterval(() => {
      getJob(authSnap, jobIdRef.current!)
        .then(setJob)
        .catch(() => {
          /* transient poll failure — keep polling */
        });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [jobActive, accessCode, jwt]);

  const handleVerify = async () => {
    if (!accessCode.trim()) return;
    try {
      const access = await getAccess({ accessCode });
      setAccessVerified(true);
      setTier(access.tier);
      setIsTrial(access.is_trial);
      setUsesRemaining(access.uses_remaining);
      setError("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError("Access code not recognized. Check your code and try again.");
      } else {
        setError("Could not verify access code. Try again.");
      }
      setAccessVerified(false);
      setTier(0);
    }
  };

  const handleSignIn = async () => {
    setLoginLoading(true);
    setLoginError("");
    const result = await authClient.signIn.email({
      email: loginEmail,
      password: loginPassword,
    });
    setLoginLoading(false);
    if (result.error) {
      setLoginError(result.error.message ?? "Sign in failed.");
    }
  };

  const handleSignUp = async () => {
    setLoginLoading(true);
    setLoginError("");
    const result = await authClient.signUp.email({
      email: loginEmail,
      password: loginPassword,
      name: loginName,
    });
    setLoginLoading(false);
    if (result.error) {
      setLoginError(result.error.message ?? "Account creation failed.");
    }
  };

  const handleSignOut = async () => {
    await authClient.signOut();
    setJwt(null);
    setTier(0);
    setIsTrial(false);
    setUsesRemaining(null);
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
  };

  // Reset everything for a fresh event, but keep the (verified) access/auth state.
  const startOver = resetCore;

  const resetForm = resetCore;

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

  const loggedInNoAccess = session.data && !session.isPending && tier === 0;

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

      <section className={`section${locked ? " form-dim" : ""}`}>
        <h2>Access</h2>
        <div className="field-grid">
          <div className="field access-col">
            <p className="field-section-label">Account</p>
            {session.isPending ? (
              <p className="hint">Checking session…</p>
            ) : session.data ? (
              <>
                <p className="account-email">{session.data.user.email}</p>
                {loggedInNoAccess && (
                  <p className="section-note">
                    This account has no broadcast access yet — contact The Commons.
                  </p>
                )}
                <button type="button" className="linklike" onClick={handleSignOut}>
                  Sign out
                </button>
              </>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="login-email">Email</label>
                  <input
                    id="login-email"
                    type="email"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    autoComplete="email"
                    disabled={loginLoading}
                  />
                </div>
                {loginMode === "signup" && (
                  <div className="field">
                    <label htmlFor="login-name">Name</label>
                    <input
                      id="login-name"
                      type="text"
                      value={loginName}
                      onChange={(e) => setLoginName(e.target.value)}
                      autoComplete="name"
                      disabled={loginLoading}
                    />
                  </div>
                )}
                <div className="field">
                  <label htmlFor="login-password">Password</label>
                  <input
                    id="login-password"
                    type="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    autoComplete={loginMode === "signin" ? "current-password" : "new-password"}
                    disabled={loginLoading}
                  />
                </div>
                {loginError && <p className="field-error">{loginError}</p>}
                <div className="actions">
                  {loginMode === "signin" ? (
                    <>
                      <button
                        type="button"
                        onClick={handleSignIn}
                        disabled={loginLoading || !loginEmail || !loginPassword}
                      >
                        {loginLoading ? "Signing in…" : "Sign in"}
                      </button>
                      <button
                        type="button"
                        className="linklike"
                        onClick={() => { setLoginMode("signup"); setLoginError(""); }}
                      >
                        Create account
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={handleSignUp}
                        disabled={loginLoading || !loginEmail || !loginPassword || !loginName}
                      >
                        {loginLoading ? "Creating…" : "Create account"}
                      </button>
                      <button
                        type="button"
                        className="linklike"
                        onClick={() => { setLoginMode("signin"); setLoginError(""); }}
                      >
                        Sign in instead
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="field access-col">
            <p className="field-section-label">Access Code</p>
            <div className="verify-row">
              <input
                id="access-code"
                type="password"
                value={accessCode}
                onChange={(e) => {
                  setAccessCode(e.target.value);
                  setAccessVerified(false);
                  if (!jwt) setTier(0);
                }}
                autoComplete="off"
                disabled={busy || job !== null || locked}
                placeholder="Provided by The Commons"
              />
              <button
                type="button"
                className={accessVerified && !jwt ? "verify is-verified" : "verify"}
                onClick={handleVerify}
                disabled={accessVerified && !jwt || accessCode.trim() === "" || !!jwt}
              >
                {accessVerified && !jwt ? "✓ Verified" : "Verify"}
              </button>
            </div>
            {isTrial && hasAccess && usesRemaining !== null && (
              <p className="hint">
                {usesRemaining} use{usesRemaining !== 1 ? "s" : ""} remaining —
                one use per event previewed; edits are free.
              </p>
            )}
            <p className="hint">Remembered on this device — you stay signed in across events.</p>
          </div>
        </div>

        <div className="contact-row">
          <div className="field">
            <label htmlFor="contact-name">Contact Name</label>
            <input
              id="contact-name"
              type="text"
              value={draft.organizer_name ?? ""}
              onChange={(e) => handleDraftChange({ ...draft, organizer_name: e.target.value })}
              disabled={busy || job !== null || !hasAccess || locked}
              maxLength={200}
            />
          </div>

          <div className="field">
            <label htmlFor="contact-email">Contact Email</label>
            <input
              id="contact-email"
              type="email"
              value={draft.contact_email ?? ""}
              onChange={(e) => handleDraftChange({ ...draft, contact_email: e.target.value })}
              disabled={busy || job !== null || !hasAccess || locked}
            />
          </div>

          <div className="field">
            <label htmlFor="contact-phone">Contact Phone</label>
            <input
              id="contact-phone"
              type="tel"
              value={draft.contact_phone ?? ""}
              onChange={(e) => handleDraftChange({ ...draft, contact_phone: e.target.value })}
              disabled={busy || job !== null || !hasAccess || locked}
              maxLength={40}
            />
          </div>

          <p className="hint contact-hint">
            Used as the organizer/submitter contact on every calendar. Remembered on this device and reused for every event.
          </p>
        </div>
      </section>

      {tier >= 2 && (
        <section className={`section${locked ? " form-dim" : ""}`}>
          <h2>AI Autofill</h2>
          <p className="hint">
            Paste a raw event description, email, or flyer text below and the AI will fill
            the event fields for you. Works on a blank event form — your saved contact
            details are fine; reset first if you've already entered event details.
          </p>
          {!isDraftEmpty(draft) ? (
            <>
              <textarea
                className="ai-autofill-textarea"
                disabled
                placeholder="Paste an event description / flyer text / email…"
                value={aiText}
              />
              <div className="actions">
                <button type="button" disabled>
                  ✨ Generate from text
                </button>
                <span className="section-note">
                  AI autofill works on a blank event form — click Reset to clear the event details first.
                </span>
              </div>
            </>
          ) : (
            <>
              <textarea
                className="ai-autofill-textarea"
                placeholder="Paste an event description / flyer text / email…"
                value={aiText}
                onChange={(e) => setAiText(e.target.value)}
                disabled={aiBusy || job !== null || locked}
              />
              <div className="actions">
                <button
                  type="button"
                  onClick={handleAiAutofill}
                  disabled={
                    aiText.trim() === "" ||
                    !isDraftEmpty(draft) ||
                    aiBusy ||
                    job !== null ||
                    locked
                  }
                >
                  {aiBusy ? "Generating…" : "✨ Generate from text"}
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {/* ── The Event form ── */}
      <section className="section">
        <div className="section-title-row">
          <h2>The Event</h2>
          <button
            type="button"
            className="reset-form-inline"
            onClick={resetForm}
            disabled={busy || aiBusy || job !== null}
            title="Clear the form and start over"
          >
            Reset form
          </button>
        </div>
        <div className={hasAccess && !locked ? "" : "form-dim"}>
          {!isDraftEmpty(draft) && (
            <p className="hint">Draft auto-saved on this device — cleared when you start over.</p>
          )}
          <EventForm draft={draft} onChange={handleDraftChange} disabled={busy || job !== null || locked} />
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
                <span className="section-note">Verify your access code or sign in to begin.</span>
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
                      <span className="target-status submitted">submitted</span>
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
                    Submit events!
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
          <JobProgress
            job={job}
            auth={auth}
            onRetry={handleRetry}
            onSubmitReal={handleSubmitReal}
            retrying={busy}
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
              Have suggestions?
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
