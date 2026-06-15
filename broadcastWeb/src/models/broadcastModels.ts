// Controlled vocabularies — mirror broadcast/routing.py on the backend.
export const LOCALITIES = [
  { value: "pittsboro", label: "Pittsboro" },
  { value: "chatham", label: "Chatham County (other)" },
  { value: "chapel-hill", label: "Chapel Hill" },
  { value: "carrboro", label: "Carrboro" },
  { value: "durham", label: "Durham" },
  { value: "raleigh", label: "Raleigh" },
  { value: "cary", label: "Cary" },
  { value: "wake", label: "Wake County (other)" },
  { value: "triangle", label: "Triangle-wide" },
] as const;

export const CATEGORIES = [
  { value: "music", label: "Music" },
  { value: "arts", label: "Arts" },
  { value: "family-kids", label: "Family & Kids" },
  { value: "wellness", label: "Wellness" },
  { value: "food-drink", label: "Food & Drink" },
  { value: "festival", label: "Festival" },
  { value: "market", label: "Market" },
  { value: "literary", label: "Literary" },
  { value: "community", label: "Community" },
  { value: "nightlife", label: "Nightlife" },
  { value: "education", label: "Education" },
] as const;

export interface EventDraft {
  title: string;
  description: string;
  start_datetime: string;
  end_datetime?: string;
  all_day: boolean;
  venue_name: string;
  address_line1: string;
  state: string;
  zip: string;
  locality: string[];
  categories: string[];
  event_url?: string;
  ticket_url?: string;
  price?: string;
  is_free: boolean;
  image_url?: string;
  organizer_name?: string;
  contact_email?: string;
  contact_phone?: string;
}

export interface EligibleSite {
  site_key: string;
  name: string;
}

export interface ExcludedSite {
  site_key: string;
  reason: string;
}

export interface PreviewResult {
  eligible: EligibleSite[];
  excluded: ExcludedSite[];
}

export type TargetStatus =
  | "pending"
  | "in_progress"
  | "succeeded"
  | "failed"
  | "needs_manual"
  | "skipped";

export interface JobTarget {
  site_key: string;
  name: string;
  status: TargetStatus;
  attempts: number;
  dry_run: boolean;
  error: string;
  external_url: string;
  screenshot_url: string;
}

export interface JobDetail {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  targets: JobTarget[];
}

// Manual-review recipe — mirrors broadcast/adapters/base.py recipe(). The
// extension fills these; the human solves the captcha and clicks submit.
export type RecipeFieldType =
  | "text"
  | "textarea"
  | "date"
  | "time"
  | "select"
  | "radio"
  | "checkbox"
  | "file"
  | "select2"
  | "terms"
  | "manual_widget";

export interface RecipeField {
  selector: string;
  type: RecipeFieldType;
  value: string;
  required: boolean;
  label: string;
  hint: string | null;
}

export interface Recipe {
  site_key: string;
  name: string;
  url: string;
  fields: RecipeField[];
  captcha_hint: string | null;
  submit_selector: string;
}
