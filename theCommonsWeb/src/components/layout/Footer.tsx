import Link from 'next/link';

const FOOTER_LINKS = {
    About: [
        { label: 'About The Commons', href: '/about' },
        { label: 'Our Mission', href: '/about#mission' },
        { label: 'How It Works', href: '/about#how-it-works' },
        { label: 'FAQ', href: '/about#faq' },
    ],
    Contribute: [
        { label: 'Post an Event', href: '#' },
        { label: 'Event Guidelines', href: '#' },
        { label: 'Submit a Correction', href: '#' },
        { label: 'Advertise With Us', href: '#' },
    ],
    Connect: [
        { label: 'Instagram', href: 'https://instagram.com' },
        { label: 'Contact Us', href: '#' },
        { label: 'Newsletter', href: '#' },
        { label: 'Feedback', href: '#' },
    ],
};

function isExternal(href: string) {
    return href.startsWith('http');
}

export function Footer() {
    const year = new Date().getFullYear();

    return (
        <footer className="mt-12 border-t-2 border-(--color-border)">

            {/* ── Follow strip ─────────────────────────────────────── */}
            <div className="max-w-300 mx-auto px-4">
                <div className="flex items-center gap-4 py-2.5">
                    <span className="flex-1 border-t border-(--color-border-light)" aria-hidden="true" />
                    <div className="flex items-center gap-3 shrink-0">
                        <span className="text-[10px] font-black uppercase tracking-[0.2em]">Follow Us</span>
                        <a
                            href="https://instagram.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[11px] uppercase tracking-wider no-underline hover:text-(--color-accent) transition-colors"
                            aria-label="Instagram"
                        >
                            Instagram
                        </a>
                        <span className="text-(--color-border-light) text-xs" aria-hidden="true">/</span>
                        <a
                            href="#"
                            className="text-[11px] uppercase tracking-wider no-underline hover:text-(--color-accent) transition-colors"
                            aria-label="Facebook"
                        >
                            Facebook
                        </a>
                    </div>
                    <span className="flex-1 border-t border-(--color-border-light)" aria-hidden="true" />
                </div>
            </div>

            {/* ── Link columns + watermark ──────────────────────────── */}
            <div className="relative overflow-hidden border-t border-(--color-border-light)">

                {/* Faint watermark title */}
                <div
                    className="absolute inset-0 flex items-center justify-center pointer-events-none select-none"
                    aria-hidden="true"
                >
                    <span
                        className="font-black text-[clamp(4rem,12vw,9rem)] leading-none text-(--color-border-light) opacity-40 tracking-tight"
                        style={{ fontFamily: 'var(--font-headline)' }}
                    >
                        The Commons
                    </span>
                </div>

                {/* Link columns */}
                <div className="relative max-w-300 mx-auto px-4 py-6 grid grid-cols-1 md:grid-cols-3 gap-6">
                    {Object.entries(FOOTER_LINKS).map(([section, links]) => (
                        <div key={section} className="text-center">
                            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-(--color-accent) mb-2">
                                {section}
                            </p>
                            <ul className="space-y-1.5 list-none p-0 m-0">
                                {links.map(link => (
                                    <li key={link.label}>
                                        {isExternal(link.href) ? (
                                            <a
                                                href={link.href}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-xs no-underline text-(--color-text) hover:text-(--color-accent) transition-colors"
                                            >
                                                {link.label}
                                            </a>
                                        ) : (
                                            <Link
                                                href={link.href}
                                                className="text-xs no-underline text-(--color-text) hover:text-(--color-accent) transition-colors"
                                            >
                                                {link.label}
                                            </Link>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Copyright bar ────────────────────────────────────── */}
            <div className="border-t-2 border-(--color-border)">
                <div className="max-w-300 mx-auto px-4 py-3 text-center">
                    <p className="text-xs text-(--color-text-muted)">
                        &copy; {year} The Commons &bull; Chapel Hill Area, N.C. &bull; All rights reserved.
                    </p>
                </div>
            </div>

        </footer>
    );
}
