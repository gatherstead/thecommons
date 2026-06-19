// Whole-page persistence so a reload (or accidental close) doesn't lose work,
// including an in-flight job. The access code is stored too — these are
// low-stakes operator codes, not credentials worth protecting from localStorage.
import type { EventDraft, JobDetail, PreviewResult } from "../models/broadcastModels";

export const STORAGE_KEY = "broadcast:state:v1";

export interface PersistBundle {
  accessCode?: string;
  verified?: boolean;
  draft?: EventDraft;
  preview?: PreviewResult | null;
  selected?: string[];
  job?: JobDetail | null;
  jobId?: string | null;
}

export const loadBundle = (): PersistBundle => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PersistBundle) : {};
  } catch {
    return {};
  }
};

const isJobFinished = (job: JobDetail | null | undefined): boolean =>
  job != null &&
  (job.status === "done" || job.status === "failed" || job.status === "canceled");

// Persist while there's unfinished work. Once a job reaches a terminal state,
// drop the saved state so a reload starts from a clean slate.
export const saveBundle = (bundle: PersistBundle): void => {
  try {
    if (isJobFinished(bundle.job)) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bundle));
  } catch {
    /* storage full or unavailable — non-fatal */
  }
};
