import { FILTER_TAGS, type TagId } from '../../constants/tags';

interface TagsBarProps {
    selectedTags: TagId[];
    onTagToggle: (tagId: TagId) => void;
}

export function TagsBar({ selectedTags, onTagToggle }: TagsBarProps) {
    return (
        <nav
            aria-label="Filter by interest"
            className="border-b-2 border-[var(--color-border)] bg-[var(--color-bg)]"
        >
            <div className="max-w-[1200px] mx-auto px-4 py-1.5 flex items-center overflow-x-auto whitespace-nowrap scrollbar-hide">
                <span className="text-[10px] font-black uppercase tracking-widest text-[var(--color-accent)] mr-3 shrink-0">
                    Filter:
                </span>

                {FILTER_TAGS.map((tag, i) => {
                    const isSelected = selectedTags.includes(tag.id);
                    return (
                        <span key={tag.id} className="flex items-center">
                            {i > 0 && (
                                <span className="mx-2 text-[var(--color-border-light)] text-xs select-none">|</span>
                            )}
                            <button
                                onClick={() => onTagToggle(tag.id)}
                                aria-pressed={isSelected}
                                className={`text-xs uppercase tracking-wider shrink-0 cursor-pointer bg-transparent border-none transition-colors ${
                                    isSelected
                                        ? 'font-black text-[var(--color-accent)] underline'
                                        : 'hover:text-[var(--color-accent)]'
                                }`}
                            >
                                {tag.label}
                            </button>
                        </span>
                    );
                })}
            </div>
        </nav>
    );
}
