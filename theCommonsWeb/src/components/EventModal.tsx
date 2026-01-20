import { FILTER_TAGS } from "./TagFilter";
import { TOWNS } from "./TownMultiselect";

interface AppEvent {
    id?: string;
    title: string;
    date: string; // This is a string
    description?: string;
    venue?: string;
    time?: string;
    price?: string;
    town?: string;
    tags?: string[];
}

interface EventModalProps {
    event: AppEvent | null;
    onClose: () => void;
}

function formatDate(dateString: string): string {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;

    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}

export function EventModal({ event, onClose }: EventModalProps) {
    if (!event) return null;

    const townName = TOWNS.find(t => t.id === event.town)?.name || event.town || "Unknown Location";

    const tagLabels = (event.tags ?? [])
        .map(tagId => FILTER_TAGS.find(t => t.id === tagId)?.label)
        .filter(Boolean);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="absolute inset-0" onClick={onClose} />

            <article className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-[var(--color-paper)] newspaper-border shadow-2xl p-8 md:p-12">
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 text-2xl hover:text-[var(--color-accent)]"
                >
                    ✕
                </button>

                <div className="border-b-2 border-black pb-4 mb-6">
                    <div className="flex justify-between items-baseline mb-2">
                        <span className="text-sm uppercase tracking-widest text-[var(--color-accent)] font-bold">
                            {townName}
                        </span>
                        <span className="font-[var(--font-accent)] text-sm">
                            {formatDate(event.date)}
                        </span>
                    </div>
                    <h2 className="font-[var(--font-headline)] text-4xl md:text-5xl font-bold leading-tight">
                        {event.title}
                    </h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
                    <div className="md:col-span-2">
                        <p className="drop-cap text-xl leading-relaxed mb-6">
                            {event.description || "No description provided."}
                        </p>
                    </div>

                    <div className="space-y-4 font-[var(--font-accent)] border-l border-[var(--color-border)] pl-6">
                        <div>
                            <h4 className="text-xs uppercase text-[var(--color-muted)] mb-1">Venue</h4>
                            <p className="font-semibold">{event.venue || "TBD"}</p>
                        </div>
                        <div>
                            <h4 className="text-xs uppercase text-[var(--color-muted)] mb-1">Time</h4>
                            <p className="font-semibold">{event.time || "TBD"}</p>
                        </div>
                        <div>
                            <h4 className="text-xs uppercase text-[var(--color-muted)] mb-1">Admission</h4>
                            <p className="text-2xl font-bold font-[var(--font-headline)]">{event.price || "Free"}</p>
                        </div>
                    </div>
                </div>

                <div className="flex flex-wrap gap-2 pt-6 border-t border-[var(--color-border)]">
                    {tagLabels.map((label, i) => (
                        <span key={i} className="text-xs uppercase tracking-wider px-3 py-1 border border-black italic">
                            #{label}
                        </span>
                    ))}
                </div>
            </article>
        </div>
    );
}