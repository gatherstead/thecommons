'use client';

import { usePathname } from 'next/navigation';
import { Header } from './Header';
import { Footer } from './Footer';
import { MessageStackBanner } from './MessageStackBanner';
import { DigestCTAPusher } from './DigestCTAPusher';

const PORTAL_PATHS = ['/signin', '/join', '/forgot-password'];

export function SiteChrome({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const isPortal = PORTAL_PATHS.some(
        path => pathname === path || pathname.startsWith(`${path}/`),
    );

    if (isPortal) {
        return <>{children}</>;
    }

    return (
        <div className="min-h-screen bg-[var(--color-bg)]">
            <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1 focus:bg-[var(--color-accent)] focus:text-white focus:text-sm"
            >
                Skip to content
            </a>
            <MessageStackBanner />
            <DigestCTAPusher delaySeconds={15} />
            <Header />
            {children}
            <Footer />
        </div>
    );
}
