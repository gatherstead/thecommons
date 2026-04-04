import type { AnchorHTMLAttributes } from 'react';

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
    external?: boolean;
}

export function Link({ external = false, children, ...props }: LinkProps) {
    const externalProps = external
        ? { target: '_blank' as const, rel: 'noopener noreferrer' }
        : {};

    return (
        <a
            className="underline hover:text-[var(--color-accent)]"
            {...externalProps}
            {...props}
        >
            {children}
        </a>
    );
}
