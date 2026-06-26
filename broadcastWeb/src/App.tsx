import { useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker from "./components/SitePicker";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import { clearDraft, loadDraft, loadSession, saveDraft, saveSession } from "./lib/persist";
import { sendFill, useExtension, WEB_STORE_URL } from "./hooks/useExtension";
import {
  aiAutofill,
  cancelJob,
  directRecipe,
  getJob,
  previewBroadcast,
  retryJob,
  submitReal,
} from "./services/broadcastApi";

const DEV_FIXTURE: EventDraft = {
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

// Returns true when the draft is functionally pristine — nothing the user has
// entered yet. State "NC" is the default and counts as empty; any other state
// value means the user (or AI) has touched it.
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
  (draft.image_url === undefined || draft.image_url.trim() === "") &&
  (draft.organizer_name === undefined || draft.organizer_name.trim() === "") &&
  (draft.contact_email === undefined || draft.contact_email.trim() === "") &&
  (draft.contact_phone === undefined || draft.contact_phone.trim() === "");

// Returns friendly labels for blank optional fields. Mirrors the empties logic
// in isDraftEmpty for the optional subset of fields.
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

export default function App() {
  const [accessCode, setAccessCode] = useState(SESSION.accessCode ?? "");
  const [verified, setVerified] = useState(SESSION.verified ?? false);
  const [draft, setDraft] = useState<EventDraft>(DRAFT.draft ?? EMPTY_DRAFT);
  const [preview, setPreview] = useState<PreviewResult | null>(DRAFT.preview ?? null);
  const [selected, setSelected] = useState<Set<string>>(new Set(DRAFT.selected ?? []));
  const [job, setJob] = useState<JobDetail | null>(DRAFT.job ?? null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiText, setAiText] = useState("");
  const [error, setError] = useState("");
  const [extFillStatus, setExtFillStatus] = useState<Record<string, ExtFillStatus>>({});
  const [speedSubmit, setSpeedSubmit] = useState(false);
  const jobIdRef = useRef<string | null>(DRAFT.jobId ?? null);
  const { installed: extInstalled, extensionId, recheck: recheckExt } = useExtension();

  const jobActive = job !== null && (job.status === "queued" || job.status === "running");

  // Session: you stay "signed in" with your access code across events/refreshes.
  useEffect(() => {
    saveSession({ accessCode, verified });
  }, [accessCode, verified]);

  // Draft: the event you're working on, auto-saved until an explicit start-over
  // (resetCore clears it). Survives refreshes even once the job finishes.
  useEffect(() => {
    saveDraft({ draft, preview, selected: [...selected], job, jobId: jobIdRef.current });
  }, [draft, preview, selected, job]);

  useEffect(() => {
    if (!jobActive || !jobIdRef.current) return;
    const id = setInterval(() => {
      getJob(accessCode, jobIdRef.current!)
        .then(setJob)
        .catch(() => {
          /* transient poll failure — keep polling */
        });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [jobActive, accessCode]);

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
    try {
      const result = await previewBroadcast(accessCode, toApiEvent(draft));
      setPreview(result);
      setSelected(new Set(result.eligible.map((s) => s.site_key)));
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
      await retryJob(accessCode, jobIdRef.current, siteKeys);
      setJob(await getJob(accessCode, jobIdRef.current));
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
      await submitReal(accessCode, jobIdRef.current, siteKeys);
      setJob(await getJob(accessCode, jobIdRef.current));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed.");
    }
  };

  const handleCancel = async () => {
    if (!jobIdRef.current) return;
    setBusy(true);
    setError("");
    try {
      await cancelJob(accessCode, jobIdRef.current);
      setJob(await getJob(accessCode, jobIdRef.current));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed.");
    } finally {
      setBusy(false);
    }
  };

  // Fills a single calendar via the extension. Called when the user clicks a
  // calendar row in the per-calendar speed-submit checklist.
  const fillOne = async (siteKey: string) => {
    if (!extensionId) {
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unavailable" }));
      return;
    }
    setExtFillStatus((prev) => ({ ...prev, [siteKey]: "filling" }));
    try {
      const recipe = await directRecipe(accessCode, toApiEvent(draft), siteKey);
      const ok = await sendFill(extensionId, recipe);
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: ok ? "submitted" : "unavailable" }));
    } catch {
      setExtFillStatus((prev) => ({ ...prev, [siteKey]: "unavailable" }));
    }
  };

  // Core reset: clears all form/job state (and the saved draft) but keeps the
  // verified access code — you stay signed in for the next event.
  const resetCore = () => {
    clearDraft();
    jobIdRef.current = null;
    setJob(null);
    setPreview(null);
    setSelected(new Set());
    setDraft(EMPTY_DRAFT);
    setError("");
    setAiText("");
    setExtFillStatus({});
    setSpeedSubmit(false);
  };

  // Reset everything for a fresh event, but keep the (verified) access code.
  const startOver = resetCore;

  // Top-of-page reset button handler (production-visible).
  const resetForm = resetCore;

  const handleAiAutofill = async () => {
    setAiBusy(true);
    setError("");
    try {
      const result = await aiAutofill(accessCode, aiText);
      setDraft({ ...EMPTY_DRAFT, ...result.event });
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

  // Derived values used in the Destinations section
  const unfilled = unfilledOptionalFields(draft);
  const nameByKey: Record<string, string> = preview
    ? Object.fromEntries(preview.eligible.map((s) => [s.site_key, s.name]))
    : {};

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
        <button
          type="button"
          className="reset-form"
          onClick={resetForm}
          disabled={busy || aiBusy || job !== null}
          title="Clear the form and start over"
        >
          Reset form
        </button>
        <h1>BROADCAST SYNDICATE</h1>
        <p className="tagline">One event in — many local calendars out.</p>
        <div className="rule-double" />
      </header>

      <section className="section">
        <h2>Access</h2>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="access-code">
              Access Code <span className="required-mark">*</span>
            </label>
            <div className="verify-row">
              <input
                id="access-code"
                type="password"
                value={accessCode}
                onChange={(e) => { setAccessCode(e.target.value); setVerified(false); }}
                autoComplete="off"
                disabled={busy || job !== null}
              />
              <button
                type="button"
                className={verified ? "verify is-verified" : "verify"}
                onClick={() => { if (accessCode.trim() !== "") setVerified(true); }}
                disabled={verified || accessCode.trim() === ""}
              >
                {verified ? "✓ Success" : "Verify"}
              </button>
            </div>
            <p className="hint">Provided by The Commons. Remembered on this device — you stay signed in across events.</p>
          </div>

          <div className="field">
            <label htmlFor="contact-name">Contact Name</label>
            <input
              id="contact-name"
              type="text"
              value={draft.organizer_name ?? ""}
              onChange={(e) => handleDraftChange({ ...draft, organizer_name: e.target.value })}
              disabled={busy || job !== null || !verified}
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
              disabled={busy || job !== null || !verified}
            />
          </div>

          <div className="field">
            <label htmlFor="contact-phone">Contact Phone</label>
            <input
              id="contact-phone"
              type="tel"
              value={draft.contact_phone ?? ""}
              onChange={(e) => handleDraftChange({ ...draft, contact_phone: e.target.value })}
              disabled={busy || job !== null || !verified}
              maxLength={40}
            />
          </div>

          <div className="field span-2">
            <p className="hint">Used as the organizer/submitter contact on every calendar.</p>
          </div>
        </div>
      </section>

      <section className="section">
        <h2>AI Autofill</h2>
        <p className="hint">
          Paste a raw event description, email, or flyer text below and the AI will fill
          the form fields for you. Only works on a completely empty form — reset first if
          you've already entered anything.
        </p>
        {!verified ? (
          <p className="section-note">Verify your access code to begin.</p>
        ) : !isDraftEmpty(draft) ? (
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
                AI autofill works only on an empty form — click Reset to clear it first.
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
              disabled={aiBusy || job !== null}
            />
            <div className="actions">
              <button
                type="button"
                onClick={handleAiAutofill}
                disabled={
                  !verified ||
                  aiText.trim() === "" ||
                  !isDraftEmpty(draft) ||
                  aiBusy ||
                  job !== null
                }
              >
                {aiBusy ? "Generating…" : "✨ Generate from text"}
              </button>
            </div>
          </>
        )}
      </section>

      <section className={`section${verified ? "" : " form-dim"}`}>
        <h2>The Event</h2>
        {!isDraftEmpty(draft) && (
          <p className="hint">Draft auto-saved on this device — cleared when you start over.</p>
        )}
        <EventForm draft={draft} onChange={handleDraftChange} disabled={busy || job !== null} />
        <div className="actions">
          <button
            type="button"
            onClick={handlePreview}
            disabled={busy || job !== null || !draftValid || accessCode.trim() === "" || !verified}
          >
            {busy && !preview ? "Checking…" : "Preview Destinations"}
          </button>
          {!verified && (
            <span className="section-note">Verify your access code to begin.</span>
          )}
          {verified && !draftValid && (
            <span className="section-note">Fill the required (*) fields to preview.</span>
          )}
        </div>
      </section>

      {preview && !job && (
        <section className="section">
          <h2>Destinations</h2>

          {/* Optional unfilled fields — hidden once the user enters speed-submit mode */}
          {!speedSubmit && unfilled.length > 0 && (
            <p className="optional-unfilled">
              <em>Not provided: {unfilled.join(", ")}</em>
            </p>
          )}

          {speedSubmit ? (
            /* Per-calendar submit checklist: one clickable row per selected site */
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
                  </li>
                );
              })}
            </ul>
          ) : (
            <>
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
                disabled={busy}
              />

              <div className="actions">
                {!extInstalled ? (
                  <span className="section-note">
                    <a href={WEB_STORE_URL} target="_blank" rel="noopener noreferrer" onClick={recheckExt}>
                      Install the Commons Broadcast extension
                    </a>{" "}
                    to autofill forms in your browser.
                  </span>
                ) : (
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
                    Speed submit events!
                  </button>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {job && (
        <section className="section">
          <h2>Progress</h2>
          <JobProgress
            job={job}
            accessCode={accessCode}
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

      {(job || preview) && (
        <section className="section">
          <div className="actions">
            <button type="button" onClick={startOver}>
              Submit another event
            </button>
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSfCZeSLpDLnKwZt-dFDnfRfdIvFUlEoYPE_OMRdPQnxpyGxlA/viewform?usp=dialog"
              target="_blank"
              rel="noopener noreferrer"
              className="btn"
            >
              Have suggestions?
            </a>
            <span className="section-note">
              Tell us which calendars/websites you'd like added, or send any other feedback.
            </span>
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
