import type { Metadata } from 'next';
import { StaticPage, StaticSection } from '../../components/layout/StaticPage';

export const metadata: Metadata = {
    title: 'Submit a Correction — The Commons',
    description: 'How to report a wrong date, venue, or listing detail on The Commons.',
};

export default function SubmitCorrectionPage() {
    return (
        <StaticPage title="Submit a Correction" tagline="Help us keep the board accurate">
            <StaticSection title="Found Something Wrong?">
                <p className="drop-cap leading-relaxed mb-4">
                    Some of our listings are pulled automatically from venue
                    calendars and community sources, and details occasionally drift
                    &mdash; a moved date, a cancelled show, a venue that changed
                    hands. If you spot one, tell us and we&rsquo;ll fix it.
                </p>
                <p className="leading-relaxed">
                    Email{' '}
                    <a href="mailto:aryav@unc.edu" className="underline">
                        aryav@unc.edu
                    </a>{' '}
                    with a link to the event (or the title, town, and date if you
                    don&rsquo;t have a link), what&rsquo;s wrong, and the correct
                    information if you know it. We review corrections by hand, so
                    the more specific you are, the faster we can fix it.
                </p>
            </StaticSection>

            <div className="rule-thick mb-8" aria-hidden="true" />

            <StaticSection title="Posted an Event Yourself?">
                <p className="leading-relaxed">
                    If it&rsquo;s a listing you submitted, the fastest fix is
                    editing it directly from your account. Otherwise, the same
                    email above works for self-posted listings too.
                </p>
            </StaticSection>
        </StaticPage>
    );
}
