import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getEvent, getTowns } from '../../../services/eventService';
import { EventDetailContent, VerifiedStamp } from '../../../components/events/EventDetailContent';

interface EventPageProps {
    params: Promise<{ uuid: string }>;
}

export async function generateMetadata({ params }: EventPageProps): Promise<Metadata> {
    const { uuid } = await params;
    const event = await getEvent(uuid);

    if (!event) {
        return { title: 'Event Not Found — The Commons' };
    }

    const description = event.description
        ? event.description.slice(0, 160)
        : `${event.title} in ${event.town}.`;

    return {
        title: `${event.title} — The Commons`,
        description,
        openGraph: {
            title: event.title,
            description,
            ...(event.photo ? { images: [event.photo] } : {}),
        },
    };
}

export default async function EventPage({ params }: EventPageProps) {
    const { uuid } = await params;
    const [event, towns] = await Promise.all([getEvent(uuid), getTowns()]);

    if (!event) notFound();

    const ld = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        name: event.title,
        startDate: event.date.toISOString(),
        location: { '@type': 'Place', name: event.venue },
        ...(event.description ? { description: event.description } : {}),
        url: `https://thecommons.town/events/${event.id}`,
        ...(event.price && event.price !== 'Not Listed'
            ? {
                  offers: {
                      '@type': 'Offer',
                      price: event.price === 'Free' ? '0' : event.price.replace('$', ''),
                      priceCurrency: 'USD',
                      availability: 'https://schema.org/InStock',
                  },
              }
            : {}),
        ...(event.sourceName
            ? { organizer: { '@type': 'Organization', name: event.sourceName } }
            : {}),
    };

    return (
        <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
            <script
                type="application/ld+json"
                dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }}
            />
            <nav className="mb-6">
                <Link
                    href="/"
                    className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors"
                >
                    &larr; Return to Feed
                </Link>
            </nav>

            <header className="mb-6 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none flex items-baseline gap-2 flex-wrap"
                    style={{ fontSize: 'clamp(1.75rem, 5vw, 2.75rem)', fontFamily: 'var(--font-headline)' }}
                >
                    <span>{event.title}</span>
                    {event.isVerified && <VerifiedStamp />}
                </h1>
            </header>

            <EventDetailContent event={event} towns={towns} />
        </main>
    );
}
