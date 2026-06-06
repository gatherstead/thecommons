import type { ReactNode } from 'react';
import { FILTER_TAGS } from '../../constants/tags';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';

interface EventFeedProps {
    events: FrontendEvent[];
    isLoading: boolean;
    onEventClick: (event: FrontendEvent) => void;
    towns: TownOption[];
    footer?: ReactNode;
    currentPage?: number;
    totalPages?: number;
    totalCount?: number;
    onNextPage?: () => void;
    onPrevPage?: () => void;
    isLoadingPage?: boolean;
    sectionName?: string | null;
}

// Section front nameplate — shown when a single category ("section") is active
function SectionNameplate({ name }: { name: string }) {
    return (
        <div className="text-center pt-5 pb-4">
            <h2
                className="font-black uppercase leading-none tracking-[0.12em]"
                style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.5rem)', fontFamily: 'var(--font-headline)' }}
            >
                {name}
            </h2>
            <span className="block mx-auto mt-3 w-20 border-t-2 border-[var(--color-accent)]" aria-hidden="true" />
        </div>
    );
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function formatShortDate(date: Date): string {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function getTownName(event: FrontendEvent, towns: TownOption[]): string {
    return towns.find(t => t.slug === event.town)?.name || String(event.town);
}

function getTagLabels(event: FrontendEvent): string[] {
    const labels: string[] = [];
    for (const id of event.tags) {
        const tag = FILTER_TAGS.find(t => t.id === id);
        if (tag) labels.push(tag.label);
    }
    return labels;
}

function handleCardKeyDown(e: React.KeyboardEvent, handler: () => void) {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handler();
    }
}

// Ornamental section rule with centered label
function SectionRule({ label }: { label: string }) {
    return (
        <div className="flex items-center gap-3 my-5" aria-hidden="true">
            <span className="flex-1 border-t-2 border-[var(--color-border)]" />
            <span className="text-[9px] uppercase tracking-[0.25em] font-black text-[var(--color-text-muted)] px-1 shrink-0">
                {label}
            </span>
            <span className="flex-1 border-t-2 border-[var(--color-border)]" />
        </div>
    );
}

// ─── FeaturedCard ─────────────────────────────────────────────────────────────
// Full editorial hero: massive headline, italic deck, drop-cap body, metadata

function FeaturedCard({
    event,
    onClick,
    towns,
}: {
    event: FrontendEvent;
    onClick: (e: FrontendEvent) => void;
    towns: TownOption[];
}) {
    const townName = getTownName(event, towns);
    const tagLabels = getTagLabels(event);

    // Always use town name as the kicker above the featured headline
    const kicker = townName;

    // First sentence becomes the italic deck / standfirst
    const firstSentence = event.description?.split(/(?<=[.!?])\s/)[0]?.trim() ?? '';
    const bodyAfterDeck =
        firstSentence && event.description && event.description.length > firstSentence.length
            ? event.description.slice(firstSentence.length).trim()
            : event.description;

    return (
        <article
            onClick={() => onClick(event)}
            onKeyDown={e => handleCardKeyDown(e, () => onClick(event))}
            tabIndex={0}
            className="cursor-pointer group py-5"
            aria-label={`Featured: ${event.title}`}
        >
            {/* Kicker line */}
            <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] uppercase tracking-[0.22em] font-black text-[var(--color-accent)] shrink-0">
                    {kicker}
                </span>
                <span className="flex-1 border-t border-[var(--color-border-light)]" aria-hidden="true" />
            </div>

            {/* Headline */}
            <h2
                className="font-black leading-[1.05] tracking-tight mb-3 group-hover:text-[var(--color-accent)] transition-colors"
                style={{ fontSize: 'clamp(2rem, 4vw, 3.25rem)', fontFamily: 'var(--font-headline)' }}
            >
                {event.title}
            </h2>

            {/* Italic deck / standfirst */}
            {firstSentence && (
                <p className="text-sm md:text-base italic text-[var(--color-text-muted)] leading-snug mb-3 border-l-2 border-[var(--color-border-light)] pl-3">
                    {firstSentence}
                </p>
            )}

            {/* Metadata — small caps style */}
            <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-3">
                {townName}&nbsp;&bull;&nbsp;{event.venue}&nbsp;&bull;&nbsp;{formatShortDate(event.date)}&nbsp;&bull;&nbsp;{event.time}
            </p>

            {/* Drop-cap body */}
            {bodyAfterDeck && (
                <p className="drop-cap text-sm leading-relaxed mb-3">
                    {bodyAfterDeck}
                </p>
            )}

            {/* Tags + price */}
            <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-[var(--color-border-light)]">
                {tagLabels.map((label, i) => (
                    <Badge key={i}>{label}</Badge>
                ))}
                <span className="ml-auto font-bold text-sm">{event.price}</span>
            </div>
        </article>
    );
}

// ─── PairColumn ───────────────────────────────────────────────────────────────
// Two events side-by-side, vertical column rule between them

function PairColumn({
    events,
    onClick,
    towns,
}: {
    events: [FrontendEvent, FrontendEvent];
    onClick: (e: FrontendEvent) => void;
    towns: TownOption[];
}) {
    return (
        <div className="grid grid-cols-2 border-t-2 border-[var(--color-border)]">
            {events.map((event, i) => {
                const townName = getTownName(event, towns);
                const tagLabels = getTagLabels(event);
                return (
                    <article
                        key={event.id}
                        onClick={() => onClick(event)}
                        onKeyDown={e => handleCardKeyDown(e, () => onClick(event))}
                        tabIndex={0}
                        className={[
                            'pt-3 pb-4 cursor-pointer group hover:bg-[var(--color-bg-alt)] transition-colors',
                            i === 0
                                ? 'pr-5 border-r border-[var(--color-border-light)]'
                                : 'pl-5',
                        ].join(' ')}
                        aria-label={event.title}
                    >
                        <p className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] mb-1">
                            {townName}
                        </p>
                        <h3 className="text-lg font-bold leading-tight mb-1.5 group-hover:text-[var(--color-accent)] transition-colors">
                            {event.title}
                        </h3>
                        <p className="text-xs text-[var(--color-text-muted)] mb-2">
                            {event.venue}&nbsp;&bull;&nbsp;{formatShortDate(event.date)}&nbsp;&bull;&nbsp;{event.time}
                        </p>
                        <p className="text-sm leading-snug line-clamp-3">
                            {event.description}
                        </p>
                        {tagLabels.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                                {tagLabels.slice(0, 2).map((l, li) => (
                                    <Badge key={li}>{l}</Badge>
                                ))}
                                <span className="ml-auto text-xs font-bold">{event.price}</span>
                            </div>
                        )}
                    </article>
                );
            })}
        </div>
    );
}

// ─── CompactRow ───────────────────────────────────────────────────────────────
// Scannable brief: date kicker | headline | venue/town | price

function CompactRow({
    event,
    onClick,
    towns,
}: {
    event: FrontendEvent;
    onClick: (e: FrontendEvent) => void;
    towns: TownOption[];
}) {
    const townName = getTownName(event, towns);
    return (
        <article
            onClick={() => onClick(event)}
            onKeyDown={e => handleCardKeyDown(e, () => onClick(event))}
            tabIndex={0}
            className="flex items-baseline gap-3 border-t border-[var(--color-border-light)] py-2 cursor-pointer group hover:bg-[var(--color-bg-alt)] transition-colors -mx-1 px-1"
            aria-label={event.title}
        >
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] font-bold shrink-0 w-12">
                {formatShortDate(event.date)}
            </span>
            <h3 className="font-bold text-sm flex-1 leading-tight group-hover:text-[var(--color-accent)] transition-colors">
                {event.title}
            </h3>
            <span className="text-xs text-[var(--color-text-muted)] shrink-0 hidden md:block">
                {townName}&nbsp;&bull;&nbsp;{event.venue}
            </span>
            <span className="text-xs font-bold shrink-0">{event.price}</span>
        </article>
    );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────
// Mirrors the feed layout (FeaturedCard -> PairColumn -> CompactRow briefs)
// with a synchronized ebbing opacity pulse.

function SkeletonLine({
    width = '100%',
    height = '0.75rem',
    className = '',
}: {
    width?: string;
    height?: string;
    className?: string;
}) {
    return (
        <span
            className={`skeleton-block block ${className}`}
            style={{ width, height }}
            aria-hidden="true"
        />
    );
}

function FeaturedSkeleton() {
    return (
        <div className="py-5" aria-hidden="true">
            <div className="flex items-center gap-2 mb-3">
                <SkeletonLine width="5rem" height="0.6rem" />
                <span className="flex-1 border-t border-[var(--color-border-light)]" />
            </div>
            <SkeletonLine width="92%" height="2.6rem" className="mb-2" />
            <SkeletonLine width="70%" height="2.6rem" className="mb-4" />
            <SkeletonLine width="80%" height="0.7rem" className="mb-3" />
            <SkeletonLine width="55%" height="0.6rem" className="mb-4" />
            <div className="space-y-2 mb-4">
                <SkeletonLine width="100%" />
                <SkeletonLine width="98%" />
                <SkeletonLine width="94%" />
                <SkeletonLine width="60%" />
            </div>
            <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border-light)]">
                <SkeletonLine width="3rem" height="0.9rem" />
                <SkeletonLine width="3rem" height="0.9rem" />
                <span className="ml-auto" />
                <SkeletonLine width="2.5rem" height="0.8rem" />
            </div>
        </div>
    );
}

function PairSkeleton() {
    return (
        <div className="grid grid-cols-2 border-t-2 border-[var(--color-border)]" aria-hidden="true">
            {[0, 1].map(i => (
                <div
                    key={i}
                    className={[
                        'pt-3 pb-4',
                        i === 0
                            ? 'pr-5 border-r border-[var(--color-border-light)]'
                            : 'pl-5',
                    ].join(' ')}
                >
                    <SkeletonLine width="4rem" height="0.55rem" className="mb-2" />
                    <SkeletonLine width="90%" height="1.2rem" className="mb-1.5" />
                    <SkeletonLine width="65%" height="1.2rem" className="mb-2" />
                    <SkeletonLine width="75%" height="0.55rem" className="mb-2" />
                    <div className="space-y-1.5">
                        <SkeletonLine width="100%" />
                        <SkeletonLine width="92%" />
                        <SkeletonLine width="70%" />
                    </div>
                </div>
            ))}
        </div>
    );
}

function BriefSkeleton() {
    return (
        <div
            className="flex items-baseline gap-3 border-t border-[var(--color-border-light)] py-3 -mx-1 px-1"
            aria-hidden="true"
        >
            <SkeletonLine width="2.5rem" height="0.6rem" />
            <span className="flex-1">
                <SkeletonLine width="85%" height="0.85rem" />
            </span>
            <SkeletonLine width="6rem" height="0.6rem" className="hidden md:block" />
            <SkeletonLine width="2rem" height="0.7rem" />
        </div>
    );
}

function FeedSkeleton() {
    return (
        <div
            className="border-t-2 border-[var(--color-border)]"
            role="status"
            aria-label="Loading events"
        >
            <FeaturedSkeleton />
            <PairSkeleton />
            <PairSkeleton />
            <SectionRule label="On the Horizon" />
            {[0, 1, 2, 3].map(i => (
                <BriefSkeleton key={i} />
            ))}
            <span className="sr-only">Loading events…</span>
        </div>
    );
}

// ─── PageNav ──────────────────────────────────────────────────────────────────

function PageNav({
    currentPage,
    totalPages,
    onPrevPage,
    onNextPage,
    isLoadingPage,
}: {
    currentPage: number;
    totalPages: number;
    onPrevPage?: () => void;
    onNextPage?: () => void;
    isLoadingPage?: boolean;
}) {
    if (totalPages <= 1) return null;
    return (
        <div className="flex items-center justify-between border-t-2 border-[var(--color-border)] mt-5 pt-4">
            <Button
                variant="secondary"
                size="sm"
                onClick={onPrevPage}
                disabled={currentPage <= 1 || isLoadingPage}
                className="disabled:opacity-30"
            >
                ← Prev
            </Button>
            <span className="text-[10px] uppercase tracking-[0.2em] font-black text-[var(--color-text-muted)]">
                {isLoadingPage ? 'Loading…' : `Page ${currentPage} of ${totalPages}`}
            </span>
            <Button
                variant="secondary"
                size="sm"
                onClick={onNextPage}
                disabled={currentPage >= totalPages || isLoadingPage}
                className="disabled:opacity-30"
            >
                Next →
            </Button>
        </div>
    );
}


// ─── EventFeed (main export) ──────────────────────────────────────────────────

export function EventFeed({ events, isLoading, onEventClick, towns, footer, currentPage = 1, totalPages = 1, totalCount = 0, onNextPage, onPrevPage, isLoadingPage = false, sectionName = null }: EventFeedProps) {
    if (isLoading) {
        return <FeedSkeleton />;
    }

    if (events.length === 0) {
        return (
            <div className="border-t-2 border-[var(--color-border)]">
                {sectionName && <SectionNameplate name={sectionName} />}
                <div className="text-center py-16">
                    <p className="italic text-[var(--color-text-muted)]">No upcoming events.</p>
                    <p className="text-xs text-[var(--color-text-muted)] mt-1">Try adjusting your filters or changing the date range in the sidebar.</p>
                </div>
                <PageNav currentPage={currentPage} totalPages={totalPages} onPrevPage={onPrevPage} onNextPage={onNextPage} isLoadingPage={isLoadingPage} />
                {footer && <div className="mt-4 border-t border-[var(--color-border-light)]">{footer}</div>}
            </div>
        );
    }

    const featured = events[0];
    const rest = events.slice(1);

    // Fill pairs greedily; any lone remainder goes to briefs
    const pairs: [FrontendEvent, FrontendEvent][] = [];
    let i = 0;
    while (i + 1 < rest.length && pairs.length < 2) {
        pairs.push([rest[i], rest[i + 1]]);
        i += 2;
    }
    const briefs = rest.slice(i);

    return (
        <div className="border-t-2 border-[var(--color-border)]">
            {sectionName && <SectionNameplate name={sectionName} />}

            <FeaturedCard event={featured} onClick={onEventClick} towns={towns} />

            {pairs.map((pair, pi) => (
                <PairColumn key={pi} events={pair} onClick={onEventClick} towns={towns} />
            ))}

            {briefs.length > 0 && (
                <>
                    <SectionRule label="On the Horizon" />
                    {briefs.map(event => (
                        <CompactRow
                            key={event.id}
                            event={event}
                            onClick={onEventClick}
                            towns={towns}
                        />
                    ))}
                </>
            )}

            <PageNav currentPage={currentPage} totalPages={totalPages} onPrevPage={onPrevPage} onNextPage={onNextPage} isLoadingPage={isLoadingPage} />

            {footer && <div className="mt-4 border-t border-[var(--color-border-light)]">{footer}</div>}
        </div>
    );
}
