import type { JobDetail, TargetStatus } from "../models/broadcastModels";
import { openScreenshot } from "../services/broadcastApi";

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
  const retryable = job.targets
    .filter((t) => t.status === "failed" || t.status === "needs_manual")
    .map((t) => t.site_key);
  const finished = job.status === "done" || job.status === "failed";
  const dryRun = job.targets.some((t) => t.dry_run);

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
        {job.targets.map((t) => (
          <li key={t.site_key}>
            <span className={`target-status ${t.status}`}>
              {STATUS_LABELS[t.status]}
            </span>
            <span className="site-name">{t.name}</span>
            {t.error && <span className="reason">— {t.error}</span>}
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
        ))}
      </ul>
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
