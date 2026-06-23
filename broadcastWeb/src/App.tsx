import { useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker from "./components/SitePicker";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import { loadBundle, saveBundle } from "./lib/persist";
import { sendFill, useExtension, WEB_STORE_URL } from "./hooks/useExtension";
import {
  aiAutofill,
  cancelJob,
  directRecipe,
  getJob,
  previewBroadcast,
  retryJob,
  submitBroadcast,
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

const POLL_MS = 3000;

const PERSISTED = loadBundle();

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

type ExtFillStatus = "idle" | "sending" | "sent" | "error";

export default function App() {
  const [accessCode, setAccessCode] = useState(PERSISTED.accessCode ?? "");
  const [verified, setVerified] = useState(PERSISTED.verified ?? false);
  const [draft, setDraft] = useState<EventDraft>(PERSISTED.draft ?? EMPTY_DRAFT);
  const [preview, setPreview] = useState<PreviewResult | null>(PERSISTED.preview ?? null);
  const [selected, setSelected] = useState<Set<string>>(new Set(PERSISTED.selected ?? []));
  const [job, setJob] = useState<JobDetail | null>(PERSISTED.job ?? null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiText, setAiText] = useState("");
  const [error, setError] = useState("");
  const [extFillStatus, setExtFillStatus] = useState<Record<string, ExtFillStatus>>({});
  const jobIdRef = useRef<string | null>(PERSISTED.jobId ?? null);
  const { installed: extInstalled, extensionId, recheck: recheckExt } = useExtension();

  const jobActive = job !== null && (job.status === "queued" || job.status === "running");

  // Persist the whole page while there's unfinished work; saveBundle clears the
  // saved state once a job reaches a terminal status.
  useEffect(() => {
    saveBundle({
      accessCode,
      verified,
      draft,
      preview,
      selected: [...selected],
      job,
      jobId: jobIdRef.current,
    });
  }, [accessCode, verified, draft, preview, selected, job]);

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

  const handleSubmit = async () => {
    setBusy(true);
    setError("");
    try {
      // Fill-first: every broadcast starts as a dry run so the operator can
      // review, then submits "ready" sites for real from the progress panel.
      const { job_id } = await submitBroadcast(
        accessCode,
        toApiEvent(draft),
        [...selected],
        true,
      );
      jobIdRef.current = job_id;
      setJob(await getJob(accessCode, job_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submit failed.");
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

  const handleExtensionAutofill = async () => {
    if (!extensionId) return;
    const sites = [...selected];
    setExtFillStatus(Object.fromEntries(sites.map((k) => [k, "sending"])));
    setError("");
    for (const siteKey of sites) {
      try {
        const recipe = await directRecipe(accessCode, toApiEvent(draft), siteKey);
        const ok = await sendFill(extensionId, recipe);
        setExtFillStatus((prev) => ({ ...prev, [siteKey]: ok ? "sent" : "error" }));
      } catch {
        setExtFillStatus((prev) => ({ ...prev, [siteKey]: "error" }));
      }
    }
  };

  // Core reset: clears all form/job state but keeps the verified access code.
  const resetCore = () => {
    jobIdRef.current = null;
    setJob(null);
    setPreview(null);
    setSelected(new Set());
    setDraft(EMPTY_DRAFT);
    setError("");
    setAiText("");
    setExtFillStatus({});
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
            <p className="hint">Provided by The Commons. Saved on this device so a reload keeps your place.</p>
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

          {/* Per-site extension fill status */}
          {Object.keys(extFillStatus).length > 0 && (
            <ul className="site-list ext-fill-status">
              {[...selected].map((key) => {
                const st = extFillStatus[key] ?? "idle";
                const label = st === "sending" ? "Opening…" : st === "sent" ? "Tab opened" : st === "error" ? "Failed" : "";
                return (
                  <li key={key} className={st === "error" ? "excluded" : undefined}>
                    <span className="site-name">{key}</span>
                    {label && <span className="reason">— {label}</span>}
                  </li>
                );
              })}
            </ul>
          )}

          <div className="actions">
            {/* Primary: extension autofill */}
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
                onClick={handleExtensionAutofill}
                disabled={busy || selected.size === 0}
              >
                {`Autofill ${selected.size} calendar${selected.size === 1 ? "" : "s"} with extension`}
              </button>
            )}

            {/* Oneshot (Playwright dry-run) — kept but disabled */}
            <button
              type="button"
              disabled
              onClick={handleSubmit}
              title="Oneshot server-side fill is coming soon"
              style={{ opacity: 0.4, cursor: "not-allowed" }}
            >
              {`Fill & review ${selected.size} calendar${selected.size === 1 ? "" : "s"}`}
            </button>
            <span className="section-note">
              The extension opens each calendar in a new tab — review and click Submit yourself.
            </span>
          </div>
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
