'use client';

import { usePathname } from 'next/navigation';
import { Header } from './Header';
import { Footer } from './Footer';
import { MessageStackBanner } from './MessageStackBanner';
import { AccountBannerPusher } from './AccountBannerPusher';
import { DigestCTAPusher } from './DigestCTAPusher';

// Routes that render as a standalone site (the auth portal) — no newspaper
// Header/Footer/banners. They own their full-screen chrome via PortalShell.
const BARE_PREFIXES = ['/signin', '/join', '/set-password', '/forgot-password'];

/**
 * Decides whether the shared newspaper chrome wraps the page. The providers in
 * the root layout stay in effect either way (the portal still uses useAuth);
 * only the visible Header/Footer/banners are gated. Server-rendered children
 * are passed straight through, so gating here doesn't force them client-side.
 */
export function SiteChrome({ children }: { children: React.ReactNode }) {
    const pathname = usePathname() ?? '';
    const isBare = BARE_PREFIXES.some(
        (p) => pathname === p || pathname.startsWith(`${p}/`),
    );

    if (isBare) {
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
            <AccountBannerPusher />
            <DigestCTAPusher delaySeconds={15} />
            <Header />
            {children}
            <Footer />
        </div>
    );
}
