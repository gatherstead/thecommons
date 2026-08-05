import Link from 'next/link';
import type { ReactNode } from 'react';

interface StaticPageProps {
    title: string;
    tagline?: string;
    children: ReactNode;
}

/**
 * Shared shell for masthead-style boilerplate pages (Contact, Guidelines,
 * Corrections, Advertising, Feedback). Mirrors the header/footer treatment
 * used on /about and /privacy-policy so these stub pages read as part of
 * the same publication, not bolted-on placeholders.
 */
export function StaticPage({ title, tagline, children }: StaticPageProps) {
    return (
        <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
            <nav className="mb-6">
                <Link
                    href="/"
                    className="text-xs uppercase tracking-wider no-underline hover:text-[var(--color-accent)] transition-colors"
                >
                    &larr; Back to Feed
                </Link>
            </nav>

            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-2"
                    style={{
                        fontSize: 'clamp(2.25rem, 6vw, 3.5rem)',
                        fontFamily: 'var(--font-headline)',
                    }}
                >
                    {title}
                </h1>
                {tagline && (
                    <p className="text-sm italic text-[var(--color-text-muted)]">{tagline}</p>
                )}
            </header>

            {children}

            <div className="border-t-2 border-[var(--color-border)] pt-4 text-center mt-8">
                <p className="text-xs italic text-[var(--color-text-muted)]">
                    The Commons &bull; Est. 2026 &bull; Chapel Hill Area, N.C.
                </p>
            </div>
        </main>
    );
}

interface StaticSectionProps {
    title: string;
    id?: string;
    children: ReactNode;
}

export function StaticSection({ title, id, children }: StaticSectionProps) {
    return (
        <section id={id} className="mb-8">
            <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
                {title}
            </h2>
            {children}
        </section>
    );
}
