'use client';

import { useAuth } from '../../hooks/useAuth';

const HEADING =
    'text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4';

export function SecuritySection() {
    const { user } = useAuth();

    if (!user) return null;

    return (
        <section id="security" className="mb-10">
            <h2 className={HEADING}>Security</h2>
            <p className="text-sm text-[var(--color-text-muted)]">
                Your account is secured with a password.
            </p>
        </section>
    );
}
