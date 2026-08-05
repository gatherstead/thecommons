import type { Metadata } from 'next';
import { StaticPage, StaticSection } from '../../components/layout/StaticPage';

export const metadata: Metadata = {
    title: 'Feedback — The Commons',
    description: 'Send suggestions and feedback about The Commons.',
};

export default function FeedbackPage() {
    return (
        <StaticPage title="Feedback" tagline="Tell us what to fix">
            <StaticSection title="Suggestions Welcome">
                <p className="drop-cap leading-relaxed mb-4">
                    The Commons is still young, and it improves fastest when people
                    who actually use it tell us what&rsquo;s missing or annoying.
                    Bad filters, a confusing step in posting, a town we should
                    cover, a feature you wish existed &mdash; we want to hear it.
                </p>
                <p className="leading-relaxed">
                    Send feedback to{' '}
                    <a href="mailto:aryav@unc.edu" className="underline">
                        aryav@unc.edu
                    </a>
                    . Short and specific beats polished &mdash; a sentence
                    describing what went wrong and what you expected is plenty.
                </p>
            </StaticSection>
        </StaticPage>
    );
}
