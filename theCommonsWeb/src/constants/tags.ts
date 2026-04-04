export const FILTER_TAGS = [
    { id: 'weekends', label: 'Weekends Only' },
    { id: 'evenings', label: 'Evenings' },
    { id: 'daytime', label: 'Daytime' },
    { id: 'free', label: 'Free' },
    { id: 'family-friendly', label: 'Family Friendly' },
    { id: 'nature', label: 'Nature' },
    { id: 'small-business', label: 'Small Business' },
    { id: 'lgbtq-friendly', label: 'LGBTQ-Friendly' },
    { id: 'speaks-spanish', label: 'Speaks Spanish' },
    { id: 'wheelchair-accessible', label: 'Wheelchair Accessible' },
] as const;

export type TagId = typeof FILTER_TAGS[number]['id'];
