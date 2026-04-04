import { Button } from '../ui/Button';
import { MiniCalendar } from './MiniCalendar';
import { FILTER_TAGS, type TagId } from '../../constants/tags';
import type { FrontendEvent } from '../../models/eventsModels';

type ViewMode = 'feed' | 'calendar';

interface SidebarProps {
    filteredCount: number;
    isLoading: boolean;
    hasFilters: boolean;
    onClearFilters: () => void;
    onPostEvent: () => void;
    viewMode: ViewMode;
    onToggleView: () => void;
    events: FrontendEvent[];
    selectedDate: Date | null;
    onDayClick: (date: Date | null) => void;
    selectedTags: TagId[];
    onTagToggle: (tagId: TagId) => void;
}

export function Sidebar({
    filteredCount,
    isLoading,
    hasFilters,
    onClearFilters,
    onPostEvent,
    viewMode,
    onToggleView,
    events,
    selectedDate,
    onDayClick,
    selectedTags,
    onTagToggle,
}: SidebarProps) {
    const today = new Date();
    const formattedDate = today.toLocaleDateString('en-US', {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric',
    });

    return (
        <aside className="space-y-3 text-sm">
            <Button variant="primary" onClick={onPostEvent} className="w-full">
                Post an Event +
            </Button>

            <hr />

            <p className="text-xs italic text-[var(--color-text-muted)] leading-snug">
                {formattedDate}
            </p>

            <hr />

            {/* Always-visible mini calendar */}
            <MiniCalendar
                events={events}
                selectedDate={selectedDate}
                onDayClick={onDayClick}
            />

            <hr />

            <button
                onClick={onToggleView}
                className="text-xs uppercase tracking-wider cursor-pointer bg-transparent border-none underline hover:text-[var(--color-accent)] block"
            >
                {viewMode === 'feed' ? '[ View Full Calendar ]' : '[ View Feed ]'}
            </button>

            <hr />

            <p className="text-xs italic text-[var(--color-text-muted)]">
                Follow{' '}
                <a
                    href="https://instagram.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="not-italic underline hover:text-[var(--color-accent)]"
                >
                    @TheCommonsLocal
                </a>
            </p>

            <hr />

            {/* Tag filters — full-width stacked rows */}
            <div>
                <p className="text-[9px] uppercase tracking-[0.18em] font-black mb-1 text-[var(--color-text-muted)]">
                    Filter by Interest
                </p>
                <div className="border-t border-[var(--color-border)]">
                    {FILTER_TAGS.map(tag => {
                        const isSelected = selectedTags.includes(tag.id);
                        return (
                            <button
                                key={tag.id}
                                onClick={() => onTagToggle(tag.id)}
                                aria-pressed={isSelected}
                                className={[
                                    'w-full flex items-center gap-2.5 text-left py-1.5 px-0',
                                    'border-b border-[var(--color-border-light)]',
                                    'cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0',
                                    'transition-colors group',
                                    isSelected
                                        ? 'text-[var(--color-accent)]'
                                        : 'text-[var(--color-text)] hover:text-[var(--color-accent)]',
                                ].join(' ')}
                            >
                                {/* Dot indicator */}
                                <span
                                    className={[
                                        'w-2 h-2 rounded-full shrink-0 border transition-colors',
                                        isSelected
                                            ? 'bg-[var(--color-accent)] border-[var(--color-accent)]'
                                            : 'border-[var(--color-border-light)] group-hover:border-[var(--color-accent)]',
                                    ].join(' ')}
                                    aria-hidden="true"
                                />
                                <span className={`text-xs uppercase tracking-wider ${isSelected ? 'font-black' : ''}`}>
                                    {tag.label}
                                </span>
                                {isSelected && (
                                    <span className="ml-auto text-[10px] text-[var(--color-accent)] font-black">✕</span>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            <hr />

            {/* Clear filters — always visible, styled by state */}
            <button
                onClick={hasFilters ? onClearFilters : undefined}
                disabled={!hasFilters}
                className={[
                    'text-xs uppercase tracking-wider cursor-pointer bg-transparent border-none block transition-colors',
                    hasFilters
                        ? 'text-[var(--color-accent)] underline hover:opacity-70'
                        : 'text-[var(--color-border-light)] cursor-default',
                ].join(' ')}
                aria-label="Clear all active filters"
            >
                Clear all filters
            </button>

            {!isLoading && (
                <>
                    <hr />
                    <p className="text-xs italic text-[var(--color-text-muted)]">
                        {filteredCount} event{filteredCount !== 1 ? 's' : ''} found
                        {selectedDate && (
                            <span> on {selectedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                        )}
                    </p>
                </>
            )}
        </aside>
    );
}
