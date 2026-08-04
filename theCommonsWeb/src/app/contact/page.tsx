import type { Metadata } from 'next';
import Link from 'next/link';
import { StaticPage, StaticSection } from '../../components/layout/StaticPage';

export const metadata: Metadata = {
    title: 'Contact Us — The Commons',
    description: 'How to get in touch with The Commons.',
};

export default function ContactPage() {
    return (
        <StaticPage title="Contact Us" tagline="Get in touch">
            <StaticSection title="Reach Us">
                <p className="drop-cap leading-relaxed mb-4">
                    The Commons is a small operation, so the fastest way to reach us
                    is email. Write to{' '}
                    <a href="mailto:aryav@unc.edu" className="underline">
                        aryav@unc.edu
                    </a>{' '}
                    with questions, listing issues, partnership inquiries, or
                    anything else &mdash; a real person reads it.
                </p>
                <p className="leading-relaxed">
                    Reporting a wrong date or venue? Use{' '}
                    <Link href="/submit-correction" className="underline">
                        Submit a Correction
                    </Link>{' '}
                    instead so it gets to the right place. Have a suggestion for the
                    site itself? See{' '}
                    <Link href="/feedback" className="underline">
                        Feedback
                    </Link>
                    .
                </p>
            </StaticSection>
        </StaticPage>
    );
}
