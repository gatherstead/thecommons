import { useRouter } from 'next/navigation';
import { Button } from '../ui/Button';
import { MiniCalendar } from './MiniCalendar';
import { FILTER_TAGS, type TagId } from '../../constants/tags';
import type { FrontendEvent } from '../../models/eventsModels';
import type { AuthUser } from '../../models/authModels';
import { DIGEST_SIGNUP_HREF } from '../layout/DigestCTAPusher';

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
    displayDate: Date;
    onNavigateMonth: (date: Date) => void;
    isLoadingMonth?: boolean;
    selectedTags: TagId[];
    onTagToggle: (tagId: TagId) => void;
    currentUser: AuthUser | null;
    onSignIn: () => void;
    onSignOut: () => void;
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
    displayDate,
    onNavigateMonth,
    isLoadingMonth = false,
    selectedTags,
    onTagToggle,
    currentUser,
    onSignIn,
    onSignOut,
}: SidebarProps) {
    const router = useRouter();
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

            {/* {currentUser ? (
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] flex items-baseline justify-between gap-2">
                    <span className="truncate">
                        Signed in as{' '}
                        <span className="not-italic font-black text-[var(--color-text)]">
                            {currentUser.business_name || currentUser.email}
                        </span>
                    </span>
                    <button
                        onClick={onSignOut}
                        className="underline hover:text-[var(--color-accent)] bg-transparent border-none cursor-pointer p-0 shrink-0"
                    >
                        Sign out
                    </button>
                </p>
            ) : (
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                    Posting an event requires an account.{' '}
                    <button
                        onClick={onSignIn}
                        className="underline hover:text-[var(--color-accent)] bg-transparent border-none cursor-pointer p-0"
                    >
                        Sign in
                    </button>
                </p>
            )} */}

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
                displayDate={displayDate}
                onNavigateMonth={onNavigateMonth}
                isLoadingMonth={isLoadingMonth}
            />

            <hr />

            <Button variant="secondary" onClick={onToggleView} className="w-full">
                {viewMode === 'feed' ? 'View Full Calendar' : 'View Feed'}
            </Button>

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

            <hr />

            <div className="border border-[var(--color-border)] px-3 py-5">
                <p className="text-[9px] uppercase tracking-[0.18em] font-black text-[var(--color-accent)] mb-[0.165rem]">
                    The Commons Digest
                </p>
                <p className="text-sm font-serif font-bold text-[var(--color-text)] leading-snug mb-[0.8rem]">
                    Every week's events, delivered to your inbox.
                </p>
                <p className="text-xs text-[var(--color-text-muted)] leading-snug mb-6">
                    The weekly digest lands every Sunday — a curated roundup of upcoming happenings in Chapel Hill &amp; Carrboro, no algorithm required.
                </p>
                <button
                    type="button"
                    onClick={() => router.push(currentUser ? '/profile' : DIGEST_SIGNUP_HREF)}
                    className="w-full text-xs uppercase tracking-[0.15em] font-black border border-[var(--color-accent)] text-[var(--color-accent)] bg-transparent py-2.5 cursor-pointer hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] transition-colors"
                >
                    {currentUser ? 'Manage digest' : "Subscribe — it's free"}
                </button>
            </div>
        </aside>
    );
}
