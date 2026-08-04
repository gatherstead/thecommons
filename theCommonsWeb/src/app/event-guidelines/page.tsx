import type { Metadata } from 'next';
import Link from 'next/link';
import { StaticPage, StaticSection } from '../../components/layout/StaticPage';

export const metadata: Metadata = {
    title: 'Event Guidelines — The Commons',
    description: 'What makes an event eligible for The Commons, and what gets rejected.',
};

export default function EventGuidelinesPage() {
    return (
        <StaticPage title="Event Guidelines" tagline="What belongs on the board">
            <StaticSection title="What Qualifies">
                <p className="drop-cap leading-relaxed mb-4">
                    The Commons lists events happening in and around the towns we
                    cover &mdash; open to the public or a specific community, with a
                    real date, time, and location. A farmers market, a book club, a
                    church potluck, a town hall, a punk show at the VFW: all fair
                    game. We do not require events to be free, but they do need to be
                    real, dated, and tied to a place someone can actually go.
                </p>
                <p className="leading-relaxed">
                    Every submission needs a title, a description, a date, and a
                    location we can resolve to one of our covered towns. Listings
                    without a recognizable town are held back rather than published
                    under the wrong place.
                </p>
            </StaticSection>

            <div className="rule-thick mb-8" aria-hidden="true" />

            <StaticSection title="What Gets Rejected">
                <p className="leading-relaxed mb-4">
                    Every submission &mdash; aggregated or self-posted &mdash; is
                    screened before it goes live. We reject spam, scams, hate speech,
                    explicit content, and anything promoting dangerous activity.
                    Purely commercial postings with no actual event attached (a sale
                    flyer with no start time, a generic ad) don&rsquo;t qualify
                    either.
                </p>
                <p className="leading-relaxed">
                    We do <em>not</em> reject something for being political,
                    religious, niche, or unconventional. The board leans permissive
                    on purpose &mdash; a protest, a prayer service, and a Dungeons
                    &amp; Dragons meetup are all welcome as long as they&rsquo;re
                    real events with a time and place.
                </p>
            </StaticSection>

            <div className="rule-thick mb-8" aria-hidden="true" />

            <StaticSection title="Submitting">
                <p className="leading-relaxed">
                    Ready to post? Head to{' '}
                    <Link href="/post" className="underline">
                        Post an Event
                    </Link>{' '}
                    and fill in the details. You&rsquo;ll need a free account.
                    Aggregated events go through the same screening automatically as
                    they&rsquo;re pulled in from local sources.
                </p>
            </StaticSection>
        </StaticPage>
    );
}
