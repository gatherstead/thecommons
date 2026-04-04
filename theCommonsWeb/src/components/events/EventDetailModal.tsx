import { FILTER_TAGS } from '../../constants/tags';
import { Modal } from '../ui/Modal';
import { Badge } from '../ui/Badge';
import { Link } from '../ui/Link';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';

interface EventDetailModalProps {
    event: FrontendEvent | null;
    onClose: () => void;
    towns?: TownOption[];
}

function formatFullDate(date: Date): string {
    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}

export function EventDetailModal({ event, onClose, towns = [] }: EventDetailModalProps) {
    if (!event) return null;

    const townName = towns.find(t => t.slug === event.town)?.name || event.town || '';
    const tagLabels = event.tags
        .map(tagId => FILTER_TAGS.find(t => t.id === tagId)?.label)
        .filter(Boolean);

    return (
        <Modal isOpen={true} onClose={onClose} title={event.title}>
            {event.photo && (
                <img
                    src={event.photo}
                    alt={event.title}
                    className="w-full max-h-56 object-cover mb-4 border border-[var(--color-border-light)]"
                />
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-4">
                <div className="md:col-span-2">
                    <p className="drop-cap leading-relaxed">
                        {event.description || 'No description provided.'}
                    </p>
                </div>
                <div className="space-y-3 text-sm border-l border-[var(--color-border-light)] pl-4">
                    <div>
                        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Venue</p>
                        <p className="font-bold">{event.venue}</p>
                    </div>
                    <div>
                        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Date</p>
                        <p className="font-bold">{formatFullDate(event.date)}</p>
                    </div>
                    <div>
                        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Time</p>
                        <p className="font-bold">{event.time}</p>
                    </div>
                    {townName && (
                        <div>
                            <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Town</p>
                            <p className="font-bold">{townName}</p>
                        </div>
                    )}
                    <div>
                        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Admission</p>
                        <p className="text-lg font-bold">{event.price || 'Free'}</p>
                    </div>
                </div>
            </div>

            {tagLabels.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-3 border-t border-[var(--color-border-light)] mb-4">
                    {tagLabels.map((label, i) => (
                        <Badge key={i}>{label}</Badge>
                    ))}
                </div>
            )}

            {event.link && (
                <div className="pt-3 border-t border-[var(--color-border-light)]">
                    <Link href={event.link} external>
                        More Info &amp; Tickets &rarr;
                    </Link>
                </div>
            )}
        </Modal>
    );
}
