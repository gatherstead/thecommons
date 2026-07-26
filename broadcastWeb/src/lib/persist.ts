// Two independent persistence scopes: session (access code + verified flag +
// contact details; never auto-cleared) and draft (current event; cleared on
// start-over). The access code is stored here — these are low-stakes operator
// codes, not credentials worth protecting from localStorage.
//
// v2: organizer/contact fields became required (see EventForm/App), which
// would strand anyone holding a v1 draft or session, so the storage keys were
// bumped and the v1 (and pre-split "state:v1") keys are actively wiped on
// first load — see clearStaleKeys(). There is no migration path forward from
// v1; a bump like this drops the accessCode/verified flag along with
// everything else, which is intended.
import type { EventDraft, JobDetail, PreviewResult } from "../models/broadcastModels";

export const SESSION_KEY = "broadcast:session:v2";
export const DRAFT_KEY = "broadcast:draft:v2";

const STALE_KEYS = ["broadcast:session:v1", "broadcast:draft:v1", "broadcast:state:v1"];

export interface SessionBundle {
  accessCode?: string;
  verified?: boolean;
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
  extFillStatus?: Record<string, string>;
  speedSubmit?: boolean;
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

// Wipe the v1 keys so they don't linger in a client's browser forever — call
// once on module load, before anything reads SESSION_KEY/DRAFT_KEY.
export const clearStaleKeys = (): void => {
  try {
    for (const key of STALE_KEYS) localStorage.removeItem(key);
  } catch {
    /* non-fatal */
  }
};

export const loadSession = (): SessionBundle => read<SessionBundle>(SESSION_KEY) ?? {};

export const saveSession = (session: SessionBundle): void => write(SESSION_KEY, session);

export const clearSession = (): void => {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* non-fatal */
  }
};

export const loadDraft = (): DraftBundle => read<DraftBundle>(DRAFT_KEY) ?? {};

export const saveDraft = (draft: DraftBundle): void => write(DRAFT_KEY, draft);

export const clearDraft = (): void => {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* non-fatal */
  }
};
