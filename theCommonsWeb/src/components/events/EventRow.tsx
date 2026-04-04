import { FILTER_TAGS } from '../../constants/tags';
import { Badge } from '../ui/Badge';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';

interface EventRowProps {
    event: FrontendEvent;
    onClick?: (event: FrontendEvent) => void;
    towns?: TownOption[];
    featured?: boolean;
}

function formatShortDate(date: Date): string {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function EventRow({ event, onClick, towns = [], featured = false }: EventRowProps) {
    const townName = towns.find(t => t.slug === event.town)?.name || String(event.town);
    const tagLabels = event.tags
        .map(tagId => FILTER_TAGS.find(t => t.id === tagId)?.label)
        .filter(Boolean);

    if (featured) {
        return (
            <article
                onClick={() => onClick?.(event)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(event); } }}
                tabIndex={0}
                role="button"
                className="border-2 border-[var(--color-border)] p-5 mb-4 cursor-pointer hover:bg-[var(--color-bg-alt)] transition-colors shadow-[3px_3px_0px_var(--color-border)]"
            >
                <p className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] mb-2 border-b border-[var(--color-border)] pb-1">
                    Featured Event
                </p>
                <h3 className="text-2xl md:text-3xl font-bold leading-tight mb-2">
                    {event.title}
                </h3>
                <p className="text-xs text-[var(--color-text-muted)] mb-3">
                    {townName} &bull; {event.venue} &bull; {formatShortDate(event.date)} &bull; {event.time}
                </p>
                <p className="drop-cap leading-relaxed mb-3">
                    {event.description}
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-[var(--color-border-light)]">
                    {tagLabels.map((label, i) => (
                        <Badge key={i}>{label}</Badge>
                    ))}
                    <span className="ml-auto font-bold text-sm">{event.price}</span>
                </div>
            </article>
        );
    }

    return (
        <article
            onClick={() => onClick?.(event)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(event); } }}
            tabIndex={0}
            role="button"
            className="border-b border-[var(--color-border-light)] py-3 cursor-pointer hover:bg-[var(--color-bg-alt)] transition-colors"
        >
            <div className="flex items-baseline gap-2 mb-1">
                <span className="text-xs uppercase tracking-wider text-[var(--color-accent)] font-bold">
                    {townName}
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                    {formatShortDate(event.date)}
                </span>
            </div>
            <h3 className="text-base font-bold leading-snug mb-1 hover:text-[var(--color-accent)] transition-colors">
                {event.title}
            </h3>
            <p className="text-xs text-[var(--color-text-muted)] mb-1">
                {event.venue} &bull; {event.time}
            </p>
            <p className="text-sm text-[var(--color-text-muted)] line-clamp-2 mb-2">
                {event.description}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
                {tagLabels.map((label, i) => (
                    <Badge key={i}>{label}</Badge>
                ))}
                <span className="ml-auto text-xs font-bold">{event.price}</span>
            </div>
        </article>
    );
}
