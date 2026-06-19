import { useState } from "react";

import type { JobDetail, JobTarget } from "../models/broadcastModels";
import { getManualRecipe, openScreenshot } from "../services/broadcastApi";
import { sendFill, useExtension, WEB_STORE_URL } from "../hooks/useExtension";

interface Props {
  job: JobDetail;
  accessCode: string;
  onRetry: (siteKeys: string[]) => void;
  onSubmitReal: (siteKeys: string[]) => void;
  retrying: boolean;
}

// What the user sees per target — derived from the backend status plus the
// dry_run flag and any optimistic local state. "ready" = filled in a dry run,
// awaiting the operator's go-ahead; "submitted" = sent for real.
type DisplayStatus =
  | "pending"
  | "in_progress"
  | "ready"
  | "submitted"
  | "needs_manual"
  | "error"
  | "skipped";

const DISPLAY_LABELS: Record<DisplayStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  ready: "Ready",
  submitted: "Submitted",
  needs_manual: "Needs manual",
  error: "Error",
  skipped: "Skipped",
};

export default function JobProgress({ job, accessCode, onRetry, onSubmitReal, retrying }: Props) {
  const { installed, extensionId, recheck } = useExtension();
  // Targets the user has acted on locally. Pure client state so the badge flips
  // immediately; the poller confirms (or a real failure overrides to "error").
  const [manualSubmitted, setManualSubmitted] = useState<Set<string>>(new Set());
  const [realSubmitted, setRealSubmitted] = useState<Set<string>>(new Set());
  const [working, setWorking] = useState<string | null>(null);
  const [manualError, setManualError] = useState("");

  const displayStatus = (t: JobTarget): DisplayStatus => {
    if (t.status === "failed") return "error"; // a real failure overrides optimism
    if (realSubmitted.has(t.site_key) || manualSubmitted.has(t.site_key)) return "submitted";
    if (t.status === "needs_manual") return "needs_manual";
    if (t.status === "succeeded") return t.dry_run ? "ready" : "submitted";
    if (t.status === "in_progress") return "in_progress";
    if (t.status === "skipped") return "skipped";
    return "pending";
  };

  const view = job.targets.map((t) => ({ target: t, status: displayStatus(t) }));
  const readyKeys = view.filter((v) => v.status === "ready").map((v) => v.target.site_key);
  const retryable = job.targets
    .filter((t) => t.status === "failed" || t.status === "needs_manual")
    .filter((t) => !manualSubmitted.has(t.site_key) && !realSubmitted.has(t.site_key))
    .map((t) => t.site_key);
  const finished =
    job.status === "done" || job.status === "failed" || job.status === "canceled";
  const dryRun = job.targets.some((t) => t.dry_run);

  // Every calendar that mattered has gone out (skipped sites don't block the
  // celebration). Drives the warm acknowledgement at the bottom of the list.
  const submittedCount = view.filter((v) => v.status === "submitted").length;
  const everythingSubmitted =
    submittedCount > 0 &&
    view.every((v) => v.status === "submitted" || v.status === "skipped");

  const openShot = (path: string) => {
    openScreenshot(accessCode, path).catch(() => {
      /* surfaced in console by the service */
    });
  };

  const handleSubmitReal = (siteKeys: string[]) => {
    if (siteKeys.length === 0) return;
    setRealSubmitted((prev) => {
      const next = new Set(prev);
      siteKeys.forEach((k) => next.add(k));
      return next;
    });
    onSubmitReal(siteKeys);
  };

  const handleManual = async (siteKey: string) => {
    if (!extensionId) return;
    setWorking(siteKey);
    setManualError("");
    try {
      const recipe = await getManualRecipe(accessCode, job.job_id, siteKey);
      const ok = await sendFill(extensionId, recipe);
      if (!ok) {
        setManualError("Couldn't reach the extension. Is it installed and enabled?");
        return;
      }
      setManualSubmitted((prev) => new Set(prev).add(siteKey));
    } catch {
      setManualError("Couldn't load the form recipe — try again.");
    } finally {
      setWorking(null);
    }
  };

  return (
    <>
      <p className="job-summary">
        {dryRun && <strong>[DRY RUN] </strong>}
        {job.status === "queued" && "Waiting for the broadcast worker to pick this up…"}
        {job.status === "running" && "Submitting, one calendar at a time…"}
        {job.status === "done" && "Broadcast complete."}
        {job.status === "failed" && "Broadcast finished with failures — see below."}
        {job.status === "canceled" && "Broadcast canceled — remaining sites were skipped."}
      </p>
      {readyKeys.length > 0 && (
        <div className="actions">
          <button
            type="button"
            className="primary"
            onClick={() => handleSubmitReal(readyKeys)}
          >
            Submit all ready ({readyKeys.length})
          </button>
        </div>
      )}
      <ul className="site-list">
        {view.map(({ target: t, status }) => (
          <li key={t.site_key}>
            <span className={`target-status ${status}`}>{DISPLAY_LABELS[status]}</span>
            <span className="site-name">{t.name}</span>
            {status === "error" && t.error && <span className="reason">— {t.error}</span>}
            {status === "ready" && (
              <>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => handleSubmitReal([t.site_key])}
                >
                  Submit
                </button>
                {t.screenshot_url && (
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => openShot(t.screenshot_url)}
                  >
                    Preview fill
                  </button>
                )}
              </>
            )}
            {/* Real submit captures the site's "thank you for submitting" page —
                show that confirmation in place of the old listing link. */}
            {status === "submitted" &&
              t.status === "succeeded" &&
              !t.dry_run &&
              t.screenshot_url && (
                <button
                  type="button"
                  className="linklike"
                  onClick={() => openShot(t.screenshot_url)}
                >
                  View confirmation
                </button>
              )}
            {status === "needs_manual" && (
              installed ? (
                <button
                  type="button"
                  className="linklike"
                  onClick={() => handleManual(t.site_key)}
                  disabled={working === t.site_key}
                >
                  {working === t.site_key ? "Opening…" : "Manual review"}
                </button>
              ) : (
                <a
                  href={WEB_STORE_URL}
                  target="_blank"
                  rel="noreferrer"
                  onClick={recheck}
                >
                  Install the helper to finish
                </a>
              )
            )}
            {/* Where the run stalled — useful for diagnosing a captcha or error. */}
            {(status === "needs_manual" || status === "error") && t.screenshot_url && (
              <button
                type="button"
                className="linklike"
                onClick={() => openShot(t.screenshot_url)}
              >
                Screenshot
              </button>
            )}
          </li>
        ))}
      </ul>
      {manualError && <p className="error-text">{manualError}</p>}
      {everythingSubmitted && (
        <p className="job-complete">
          That’s all {submittedCount}{" "}
          {submittedCount === 1 ? "calendar" : "calendars"} submitted — thank you
          for getting the word out. Your event is on its way to the community.
        </p>
      )}
      {finished && retryable.length > 0 && (
        <div className="actions">
          <button type="button" onClick={() => onRetry(retryable)} disabled={retrying}>
            {retrying ? "Re-queuing…" : `Retry ${retryable.length} unfinished`}
          </button>
        </div>
      )}
    </>
  );
}
