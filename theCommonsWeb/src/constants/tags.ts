export const FILTER_TAGS = [
    { id: 'weekends', label: 'Weekends' },
    { id: 'evenings', label: 'Evenings' },
    { id: 'daytime', label: 'Daytime' },
    { id: 'free', label: 'Free' },
    { id: 'family-friendly', label: 'Family Friendly' },
    { id: 'nature', label: 'Nature' },
    { id: 'small-business', label: 'Small Business' },
    { id: 'wheelchair-accessible', label: 'Wheelchair Accessible' },
] as const;

export type TagId = typeof FILTER_TAGS[number]['id'];

// Day-part slugs (weekends/evenings/daytime) are computed server-side from the
// event's date/time at publish — `apply_tags` in backendServer/events/tagging.py
// strips whatever was supplied and re-derives them, so offering them as a manual
// choice on the submission form is misleading (the pick is silently discarded).
// Sidebar filtering still needs all 8 slugs, so this derives a submission-only
// subset from FILTER_TAGS rather than touching FILTER_TAGS itself.
const DAY_PART_TAG_IDS = new Set<TagId>(['weekends', 'evenings', 'daytime']);

export const SUBMISSION_TAGS = FILTER_TAGS.filter(tag => !DAY_PART_TAG_IDS.has(tag.id));
