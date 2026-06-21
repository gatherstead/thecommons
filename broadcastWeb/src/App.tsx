import { useEffect, useRef, useState } from "react";

import EventForm from "./components/EventForm";
import JobProgress from "./components/JobProgress";
import SitePicker from "./components/SitePicker";
import type { EventDraft, JobDetail, PreviewResult } from "./models/broadcastModels";
import { loadBundle, saveBundle } from "./lib/persist";
import {
  cancelJob,
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

export default function App() {
  const [accessCode, setAccessCode] = useState(PERSISTED.accessCode ?? "");
  const [verified, setVerified] = useState(PERSISTED.verified ?? false);
  const [draft, setDraft] = useState<EventDraft>(PERSISTED.draft ?? EMPTY_DRAFT);
  const [preview, setPreview] = useState<PreviewResult | null>(PERSISTED.preview ?? null);
  const [selected, setSelected] = useState<Set<string>>(new Set(PERSISTED.selected ?? []));
  const [job, setJob] = useState<JobDetail | null>(PERSISTED.job ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const jobIdRef = useRef<string | null>(PERSISTED.jobId ?? null);

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

  // Reset everything for a fresh event, but keep the (verified) access code.
  const startOver = () => {
    jobIdRef.current = null;
    setJob(null);
    setPreview(null);
    setSelected(new Set());
    setDraft(EMPTY_DRAFT);
    setError("");
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
        <div className="actions">
          <button type="button" disabled title="Coming soon">
            ✨ Generate from a link or flyer
          </button>
          <span className="section-note">Coming soon — paste an event link and we'll fill the form for you.</span>
        </div>
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
          <div className="actions">
            <button
              type="button"
              className="dark"
              onClick={handleSubmit}
              disabled={busy || selected.size === 0}
            >
              {busy
                ? "Filling…"
                : `Fill & review ${selected.size} calendar${selected.size === 1 ? "" : "s"}`}
            </button>
            <span className="section-note">
              Forms are filled for your review first — submit the ready ones below.
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
