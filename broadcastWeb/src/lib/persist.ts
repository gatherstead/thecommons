// Two independent persistence scopes so the page reload (or accidental close)
// keeps your place without the two concerns clobbering each other:
//
//   session — your access code + verified flag + operator contact details
//             (name/email/phone). You stay "signed in" on this device across
//             events and refreshes; never auto-cleared.
//   draft   — the event you're working on (form, preview, picks, running job).
//             Survives refreshes even once the job finishes; cleared only on an
//             explicit start-over.
//
// The access code lives in the session scope: these are low-stakes operator
// codes, not credentials worth protecting from localStorage.
import type { EventDraft, JobDetail, PreviewResult } from "../models/broadcastModels";

export const SESSION_KEY = "broadcast:session:v1";
export const DRAFT_KEY = "broadcast:draft:v1";

// Legacy single-bundle key (pre-split). Read once for migration, never written.
const LEGACY_KEY = "broadcast:state:v1";

export interface SessionBundle {
  accessCode?: string;
  verified?: boolean;
  // Operator contact, sticky like the access code — reused across events.
  organizer_name?: string;
  contact_email?: string;
  contact_phone?: string;
}

export interface DraftBundle {
  draft?: EventDraft;
  preview?: PreviewResult | null;
  selected?: string[];
  job?: JobDetail | null;
  jobId?: string | null;
}

const read = <T>(key: string): T | null => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
};

const write = (key: string, value: unknown): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or unavailable — non-fatal */
  }
};

// One-time migration: if the new keys are absent but the old fused bundle is
// present, seed from it so existing operators don't lose their place.
const legacy = (): (SessionBundle & DraftBundle) | null => read(LEGACY_KEY);

export const loadSession = (): SessionBundle => {
  const fresh = read<SessionBundle>(SESSION_KEY);
  if (fresh) return fresh;
  const old = legacy();
  if (!old) return {};
  return {
    accessCode: old.accessCode,
    verified: old.verified,
    organizer_name: old.draft?.organizer_name,
    contact_email: old.draft?.contact_email,
    contact_phone: old.draft?.contact_phone,
  };
};

export const saveSession = (session: SessionBundle): void => write(SESSION_KEY, session);

export const clearSession = (): void => {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* non-fatal */
  }
};

export const loadDraft = (): DraftBundle => {
  const fresh = read<DraftBundle>(DRAFT_KEY);
  if (fresh) return fresh;
  const old = legacy();
  return old
    ? { draft: old.draft, preview: old.preview, selected: old.selected, job: old.job, jobId: old.jobId }
    : {};
};

export const saveDraft = (draft: DraftBundle): void => write(DRAFT_KEY, draft);

export const clearDraft = (): void => {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* non-fatal */
  }
};
