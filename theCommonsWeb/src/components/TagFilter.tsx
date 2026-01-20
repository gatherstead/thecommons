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

interface TagFilterProps {
    selectedTags: TagId[];
    onTagToggle: (tagId: TagId) => void;
}

export function TagFilter({ selectedTags, onTagToggle }: TagFilterProps) {
    return (
        <div className="border-t-2 border-b-2 border-[var(--color-border)] py-4">
            <h3 className="font-[var(--font-headline)] text-sm uppercase tracking-widest mb-3 font-semibold">
                Filter by Interest
            </h3>
            <div className="flex flex-wrap gap-2">
                {FILTER_TAGS.map((tag) => {
                    const isSelected = selectedTags.includes(tag.id);
                    return (
                        <button
                            key={tag.id}
                            onClick={() => onTagToggle(tag.id)}
                            className={`px-3 py-1.5 text-sm border-2 transition-all cursor-pointer font-[var(--font-body)] ${isSelected
                                    ? 'bg-[var(--color-ink)] text-[var(--color-paper)] border-[var(--color-ink)]'
                                    : 'bg-transparent text-[var(--color-ink)] border-[var(--color-border)] hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)]'
                                }`}
                        >
                            {tag.label}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
