import { useState } from "react";

import type { JobDetail, TargetStatus } from "../models/broadcastModels";
import { getManualRecipe, openScreenshot } from "../services/broadcastApi";
import { sendFill, useExtension, WEB_STORE_URL } from "../hooks/useExtension";

interface Props {
  job: JobDetail;
  accessCode: string;
  onRetry: (siteKeys: string[]) => void;
  retrying: boolean;
}

const STATUS_LABELS: Record<TargetStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  succeeded: "Submitted",
  failed: "Failed",
  needs_manual: "Needs manual",
  skipped: "Skipped",
};

export default function JobProgress({ job, accessCode, onRetry, retrying }: Props) {
  const { installed, extensionId } = useExtension();
  // Targets the user has handled via the manual-review extension. Pure client
  // state — the backend has no success path, so the poller keeps reporting
  // needs_manual; we optimistically show these as submitted regardless.
  const [submitted, setSubmitted] = useState<Set<string>>(new Set());
  const [working, setWorking] = useState<string | null>(null);
  const [manualError, setManualError] = useState("");

  const retryable = job.targets
    .filter((t) => t.status === "failed" || t.status === "needs_manual")
    .filter((t) => !submitted.has(t.site_key))
    .map((t) => t.site_key);
  const finished = job.status === "done" || job.status === "failed";
  const dryRun = job.targets.some((t) => t.dry_run);

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
      setSubmitted((prev) => new Set(prev).add(siteKey));
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
      </p>
      <ul className="site-list">
        {job.targets.map((t) => {
          const isSubmitted = submitted.has(t.site_key);
          return (
            <li key={t.site_key}>
              <span className={`target-status ${isSubmitted ? "succeeded" : t.status}`}>
                {isSubmitted ? "Event submitted" : STATUS_LABELS[t.status]}
              </span>
              <span className="site-name">{t.name}</span>
              {!isSubmitted && t.error && <span className="reason">— {t.error}</span>}
              {t.status === "needs_manual" && !isSubmitted && (
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
                  <a href={WEB_STORE_URL} target="_blank" rel="noreferrer">
                    Install the helper to finish
                  </a>
                )
              )}
              {t.external_url && (
                <a href={t.external_url} target="_blank" rel="noreferrer">
                  listing
                </a>
              )}
              {t.screenshot_url && (
                <button
                  type="button"
                  className="linklike"
                  onClick={() => {
                    openScreenshot(accessCode, t.screenshot_url).catch(() => {
                      /* surfaced in console by the service */
                    });
                  }}
                >
                  screenshot
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {manualError && <p className="error-text">{manualError}</p>}
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
