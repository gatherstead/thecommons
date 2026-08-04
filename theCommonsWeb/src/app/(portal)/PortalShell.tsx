'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

function portalHref(base: string, redirectTo: string | null) {
    if (!redirectTo) return base;
    return `${base}?redirect_to=${encodeURIComponent(redirectTo)}`;
}

export function PortalShell({
    activeTab,
    heading,
    subheading,
    children,
}: {
    activeTab?: 'signin' | 'join';
    heading?: string;
    subheading?: string;
    children: React.ReactNode;
}) {
    const searchParams = useSearchParams();
    const redirectTo = searchParams.get('redirect_to');

    const signInHref = portalHref('/signin', redirectTo);
    const joinHref = portalHref('/join', redirectTo);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 min-h-screen">
            {/* ── Left panel: masthead ────────────────────────────────────────── */}
            <div className="hidden md:flex md:items-center md:justify-center relative bg-[var(--color-bg-alt)] border-r border-[var(--color-border)] px-12">
                <div className="max-w-sm">
                    <span className="block text-xs uppercase tracking-[0.35em] text-[var(--color-text-muted)] mb-6">
                        Est. 2026
                    </span>
                    <h2
                        className="font-black leading-[0.95] mb-6"
                        style={{ fontSize: 'clamp(2.5rem, 6vw, 4rem)', fontFamily: 'var(--font-headline)' }}
                    >
                        The Commons
                    </h2>
                    <div className="border-t-2 border-[var(--color-border)] pt-6">
                        <p className="font-[var(--font-headline)] italic text-lg leading-relaxed text-[var(--color-text-muted)]">
                            &ldquo;Find your next excuse to stay local.&rdquo;
                        </p>
                    </div>
                    <div className="border-t border-[var(--color-border-light)] mt-8 pt-4">
                        <span className="text-xs uppercase tracking-[0.2em] text-[var(--color-text-muted)]">
                            Your town&rsquo;s digital gathering place
                        </span>
                    </div>
                </div>
            </div>

            {/* ── Right panel: form slot ─────────────────────────────────────── */}
            <div className="flex items-center justify-center px-4 py-12">
                <div className="w-full max-w-[480px]">
                    {(heading || subheading) && (
                        <header className="mb-8">
                            {heading && (
                                <h1
                                    className="font-black tracking-tight leading-none mb-1"
                                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                                >
                                    {heading}
                                </h1>
                            )}
                            {subheading && (
                                <p className="text-sm italic text-[var(--color-text-muted)]">
                                    {subheading}
                                </p>
                            )}
                        </header>
                    )}

                    <nav
                        aria-label="Account access"
                        className="flex border-b border-[var(--color-border)] mb-8"
                    >
                        <Link
                            href={signInHref}
                            aria-current={activeTab === 'signin' ? 'page' : undefined}
                            className={`px-4 py-2.5 text-xs uppercase tracking-[0.15em] font-bold text-center flex-1 -mb-px border-b-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                                activeTab === 'signin'
                                    ? 'border-[var(--color-accent)] text-[var(--color-text)]'
                                    : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                            }`}
                        >
                            Sign In
                        </Link>
                        <Link
                            href={joinHref}
                            aria-current={activeTab === 'join' ? 'page' : undefined}
                            className={`px-4 py-2.5 text-xs uppercase tracking-[0.15em] font-bold text-center flex-1 -mb-px border-b-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                                activeTab === 'join'
                                    ? 'border-[var(--color-accent)] text-[var(--color-text)]'
                                    : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                            }`}
                        >
                            Create Account
                        </Link>
                    </nav>

                    {children}
                </div>
            </div>
        </div>
    );
}
