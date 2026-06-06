import { Modal } from '../ui/Modal';
import { Link } from '../ui/Link';
import { EventDetailContent, VerifiedStamp } from './EventDetailContent';
import type { FrontendEvent, TownOption } from '../../models/eventsModels';

interface EventDetailModalProps {
    event: FrontendEvent | null;
    onClose: () => void;
    towns?: TownOption[];
}

export function EventDetailModal({ event, onClose, towns = [] }: EventDetailModalProps) {
    if (!event) return null;

    return (
        <Modal isOpen={true} onClose={onClose} title={
            <span className="flex items-baseline gap-2 flex-wrap">
                <span>{event.title}</span>
                {event.isVerified && <VerifiedStamp />}
            </span>
        }>
            <EventDetailContent event={event} towns={towns} />

            <div className="pt-3 mt-1 border-t border-[var(--color-border-light)]">
                <Link href={`/events/${event.id}`}>
                    View full page &rarr;
                </Link>
            </div>
        </Modal>
    );
}
