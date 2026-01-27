import type { TagId } from './TagFilter';
import type { TownId } from './TownMultiselect';
import { FILTER_TAGS } from './TagFilter';
import { TOWNS } from './TownMultiselect';

export interface Event {
    id: string;
    title: string;
    venue: string;
    date: Date;
    time: string;
    description: string;
    tags: String[];
    town: String;
    price: string;
    imageUrl?: string;
}

interface EventCardProps {
    event: Event;
    featured?: boolean;
    onClick?: (event: Event) => void; // Add this prop
}

function formatDate(date: Date): string {
    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}

export function EventCard({ event, featured = false, onClick }: EventCardProps) {
    const townName = TOWNS.find(t => t.id === event.town)?.name || event.town;
    const tagLabels = event.tags
        .map(tagId => FILTER_TAGS.find(t => t.id === tagId)?.label)
        .filter(Boolean);

    const commonClasses = "cursor-pointer transition-all hover:opacity-90 active:scale-[0.99]";

    if (featured) {
        return (
            <article
                onClick={() => onClick?.(event)}
                className={`newspaper-border bg-[var(--color-paper)] p-6 mb-6 ${commonClasses}`}
            >
                <div className="border-b-2 border-[var(--color-border)] pb-2 mb-4">
                    <span className="text-xs uppercase tracking-widest text-[var(--color-muted)]">
                        Featured Event
                    </span>
                </div>

                <h2 className="font-[var(--font-headline)] text-3xl md:text-4xl font-bold mb-3 leading-tight">
                    {event.title}
                </h2>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-[var(--color-muted)] mb-4 font-[var(--font-accent)]">
                    <span>{townName}</span>
                    <span>•</span>
                    <span>{event.venue}</span>
                    <span>•</span>
                    <span>{formatDate(event.date)}</span>
                    <span>•</span>
                    <span>{event.time}</span>
                </div>

                <p className="drop-cap text-lg leading-relaxed mb-4">
                    {event.description}
                </p>

                <div className="flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-[var(--color-border)]">
                    <div className="flex flex-wrap gap-2">
                        {tagLabels.map((label, i) => (
                            <span key={i} className="text-xs uppercase tracking-wider px-2 py-1 border border-[var(--color-border)]">
                                {label}
                            </span>
                        ))}
                    </div>
                    <span className="font-[var(--font-headline)] text-lg font-semibold">
                        {event.price}
                    </span>
                </div>
            </article>
        );
    }

    return (
        <article
            onClick={() => onClick?.(event)}
            className={`border-b-2 border-[var(--color-border)] pb-4 mb-4 last:border-b-0 ${commonClasses}`}
        >
            <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1">
                    <div className="flex items-baseline gap-2 mb-1">
                        <span className="text-xs uppercase tracking-wider text-[var(--color-accent)] font-semibold">
                            {townName}
                        </span>
                        <span className="text-xs text-[var(--color-muted)]">
                            {formatDate(event.date)}
                        </span>
                    </div>

                    <h3 className="font-[var(--font-headline)] text-xl font-bold mb-2 leading-tight hover:text-[var(--color-accent)] transition-colors cursor-pointer">
                        {event.title}
                    </h3>

                    <p className="text-sm text-[var(--color-muted)] mb-2 font-[var(--font-accent)]">
                        {event.venue} • {event.time}
                    </p>

                    <p className="text-sm line-clamp-2 mb-3">
                        {event.description}
                    </p>

                    <div className="flex flex-wrap items-center gap-2">
                        {tagLabels.map((label, i) => (
                            <span key={i} className="text-xs px-2 py-0.5 bg-[#ebe7de]">
                                {label}
                            </span>
                        ))}
                        <span className="ml-auto text-sm font-semibold">
                            {event.price}
                        </span>
                    </div>
                </div>
            </div>
        </article>
    );
}
