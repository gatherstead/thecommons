import type { ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'link';
    size?: 'sm' | 'md';
}

export function Button({ variant = 'secondary', size = 'md', className = '', children, ...props }: ButtonProps) {
    const base = 'font-[var(--font-sans)] cursor-pointer transition-colors tracking-wide uppercase text-xs font-bold';

    const variants = {
        primary: 'bg-[var(--color-text)] text-[var(--color-bg)] border-2 border-[var(--color-text)] hover:bg-[var(--color-accent)] hover:border-[var(--color-accent)]',
        secondary: 'bg-transparent border border-[var(--color-border)] hover:bg-[var(--color-bg-alt)]',
        link: 'bg-transparent border-none text-[var(--color-text)] underline p-0 hover:text-[var(--color-accent)] normal-case tracking-normal',
    };

    const sizes = {
        sm: 'px-3 py-1',
        md: 'px-4 py-2.5',
    };

    const sizeClass = variant === 'link' ? '' : sizes[size];

    return (
        <button
            className={`${base} ${variants[variant]} ${sizeClass} ${className}`}
            {...props}
        >
            {children}
        </button>
    );
}
