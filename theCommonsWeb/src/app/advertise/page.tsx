import type { Metadata } from 'next';
import Link from 'next/link';
import { StaticPage, StaticSection } from '../../components/layout/StaticPage';

export const metadata: Metadata = {
    title: 'Advertise With Us — The Commons',
    description: 'How local businesses and venues can promote events on The Commons.',
};

export default function AdvertisePage() {
    return (
        <StaticPage title="Advertise With Us" tagline="For local businesses and venues">
            <StaticSection title="Business &amp; Venue Accounts">
                <p className="drop-cap leading-relaxed mb-4">
                    The Commons doesn&rsquo;t sell banner ads or sponsored feeds
                    &mdash; the board stays chronological for everyone. What we do
                    offer is a business or venue account, which lets you post your
                    own events directly under your name, no waiting on aggregation.
                </p>
                <p className="leading-relaxed">
                    If you run a shop, restaurant, taproom, gallery, or event space,
                    sign up from your{' '}
                    <Link href="/dashboard" className="underline">
                        dashboard
                    </Link>{' '}
                    and choose a business or venue account type. From there you can
                    post events, edit them, and keep your listings current.
                </p>
            </StaticSection>

            <div className="rule-thick mb-8" aria-hidden="true" />

            <StaticSection title="Something Bigger in Mind?">
                <p className="leading-relaxed">
                    For partnerships beyond a standard business account &mdash;
                    recurring series, town-wide sponsorships, that sort of thing
                    &mdash; email{' '}
                    <a href="mailto:aryav@unc.edu" className="underline">
                        aryav@unc.edu
                    </a>{' '}
                    and tell us what you have in mind.
                </p>
            </StaticSection>
        </StaticPage>
    );
}
