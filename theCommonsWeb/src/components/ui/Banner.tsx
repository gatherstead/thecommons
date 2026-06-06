'use client';

import React, { useEffect, useState } from 'react';

interface BannerProps {
    children: React.ReactNode;
    onDismiss?: () => void;
    /** Show the × button. Default: true when onDismiss is provided. */
    showDismissButton?: boolean;
    /** Clicking anywhere on the banner body also calls onDismiss. Default: true. */
    dismissOnClick?: boolean;
    /** Stick to the top and hide when scrolling down, reveal when scrolling up. */
    sticky?: boolean;
    variant?: 'default' | 'accent';
}

export function Banner({
    children,
    onDismiss,
    showDismissButton = true,
    dismissOnClick = true,
    sticky = false,
    variant = 'default',
}: BannerProps) {
    const [scrollHidden, setScrollHidden] = useState(false);

    useEffect(() => {
        if (!sticky) return;
        let lastY = window.scrollY;
        const onScroll = () => {
            const y = window.scrollY;
            if (y > lastY && y > 80) setScrollHidden(true);
            else if (y < lastY) setScrollHidden(false);
            lastY = y;
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        return () => window.removeEventListener('scroll', onScroll);
    }, [sticky]);

    const borderColor =
        variant === 'accent'
            ? 'border-[var(--color-accent)]'
            : 'border-[var(--color-border)]';

    const handleBannerClick = onDismiss && dismissOnClick ? onDismiss : undefined;

    return (
        <div
            className={[
                `border-y-2 ${borderColor} bg-[var(--color-bg-alt)]`,
                sticky ? 'sticky top-0 z-40 transition-transform duration-300 ease-in-out' : '',
                sticky && scrollHidden ? '-translate-y-full' : 'translate-y-0',
                handleBannerClick ? 'cursor-pointer' : '',
            ].join(' ')}
            onClick={handleBannerClick}
        >
            <div className="max-w-300 mx-auto px-4 py-2 flex items-center justify-between gap-4">
                <div className="flex-1">{children}</div>
                {onDismiss && showDismissButton && (
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onDismiss(); }}
                        aria-label="Dismiss"
                        className="text-[var(--color-text-muted)] text-lg leading-none bg-transparent border-none cursor-pointer p-0 shrink-0 hover:text-[var(--color-text)]"
                    >
                        &times;
                    </button>
                )}
            </div>
        </div>
    );
}
