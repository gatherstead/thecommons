import type { ReactNode } from 'react';

interface BadgeProps {
    children: ReactNode;
    active?: boolean;
}

export function Badge({ children, active = false }: BadgeProps) {
    return (
        <span
            className={`inline-block px-1.5 py-0.5 text-[10px] uppercase tracking-wider border ${
                active
                    ? 'bg-[var(--color-text)] text-[var(--color-bg)] border-[var(--color-text)]'
                    : 'border-[var(--color-border-light)] text-[var(--color-text-muted)]'
            }`}
        >
            {children}
        </span>
    );
}
