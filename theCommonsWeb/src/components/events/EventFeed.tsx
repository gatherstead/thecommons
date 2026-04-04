import { FILTER_TAGS } from '../../constants/tags';
import { Badge } from '../ui/Badge';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';

interface EventFeedProps {
    events: FrontendEvent[];
    isLoading: boolean;
    onEventClick: (event: FrontendEvent) => void;
    towns: TownOption[];
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

// ─── EventFeed (main export) ──────────────────────────────────────────────────

export function EventFeed({ events, isLoading, onEventClick, towns }: EventFeedProps) {
    if (isLoading) {
        return (
            <p className="text-center py-16 italic text-[var(--color-text-muted)]">
                Loading events...
            </p>
        );
    }

    if (events.length === 0) {
        return (
            <div className="text-center py-16">
                <p className="italic text-[var(--color-text-muted)]">No events match your current filters.</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-1">Try adjusting your selections.</p>
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
        </div>
    );
}
