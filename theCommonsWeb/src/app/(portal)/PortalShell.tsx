'use client';

import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes } from 'react';
import Image from 'next/image';
import Link from 'next/link';

type PortalTab = 'signin' | 'join';

const TABS: { tab: PortalTab; label: string; href: string }[] = [
    { tab: 'signin', label: 'Sign In', href: '/signin' },
    { tab: 'join', label: 'Create Account', href: '/join' },
];

/**
 * Standalone chrome for the auth portal — a full-bleed split panel that is
 * intentionally NOT the newspaper site (no Header/Footer; see SiteChrome).
 * Left: the gilt tree painting. Right: masthead + tab switcher + form slot.
 */
export function PortalShell({
    activeTab,
    children,
}: {
    activeTab?: PortalTab;
    children: React.ReactNode;
}) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 min-h-screen bg-[var(--color-bg)]">
            {/* Left — the painting, full bleed, hidden on small screens */}
            <div className="relative hidden md:block">
                <Image
                    src="/portal-landscape.jpg"
                    alt=""
                    fill
                    sizes="50vw"
                    priority
                    className="object-cover"
                />
            </div>

            {/* Right — masthead, tabs, and the form slot */}
            <div className="flex items-center justify-center px-8 py-12 md:px-16">
                <div className="w-full max-w-[440px]">
                    <h1
                        className="text-4xl md:text-5xl font-bold tracking-tight border-b border-[var(--color-border)] pb-4 mb-3"
                        style={{ fontFamily: 'var(--font-headline)' }}
                    >
                        The Commons
                    </h1>
                    <p className="text-sm italic text-[var(--color-text-muted)]">
                        Local happenings, small NC towns.
                    </p>

                    <nav
                        aria-label="Portal navigation"
                        className="mt-8 flex gap-8 border-b border-[var(--color-border)]"
                    >
                        {TABS.map(({ tab, label, href }) => {
                            const isActive = tab === activeTab;
                            return (
                                <Link
                                    key={tab}
                                    href={href}
                                    aria-current={isActive ? 'page' : undefined}
                                    className={`-mb-px pb-3 text-xs uppercase tracking-[0.2em] no-underline transition-colors ${
                                        isActive
                                            ? 'border-b-2 border-[var(--color-gold)] font-black text-[var(--color-text)]'
                                            : 'font-bold text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                                    }`}
                                >
                                    {label}
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="mt-8">{children}</div>
                </div>
            </div>
        </div>
    );
}

/** Underline-style field matching the portal painting aesthetic. */
export function PortalField({
    label,
    ...props
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
    const generatedId = useId();
    const id = props.id ?? generatedId;
    return (
        <div>
            <label
                htmlFor={id}
                className="block text-xs uppercase tracking-[0.2em] font-bold text-[var(--color-text-muted)] mb-2"
            >
                {label}
            </label>
            <input
                id={id}
                className="w-full bg-transparent border-0 border-b border-[var(--color-border)] pb-2 text-base text-[var(--color-text)] outline-none transition-colors focus:border-[var(--color-gold)] placeholder:text-[var(--color-gold)] placeholder:opacity-60"
                {...props}
            />
        </div>
    );
}

/** Full-width charcoal submit button (serif, sentence case) per the mockup. */
export function PortalSubmit({
    children,
    className = '',
    ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button
            className={`w-full bg-[var(--color-text)] text-[var(--color-bg)] py-4 text-base tracking-wide cursor-pointer transition-opacity hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
            style={{ fontFamily: 'var(--font-headline)' }}
            {...props}
        >
            {children}
        </button>
    );
}
