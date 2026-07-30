'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '../../hooks/useAuth';

const AUTH_ORIGIN = process.env.NEXT_PUBLIC_BETTER_AUTH_URL ?? 'http://localhost:3000';

export function HeaderAuthNav() {
    const { isAuthenticated, isInitializing, user, logout } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const isOnHome = pathname === '/';

    if (isInitializing) return null;

    if (!isAuthenticated) {
        const navLinkClass = "text-[11px] uppercase tracking-widest no-underline hover:text-[var(--color-accent)] transition-colors bg-transparent border-none cursor-pointer p-0";
        const sep = <span className="text-[var(--color-border-light)] text-xs" aria-hidden="true">/</span>;

        const redirectTo = () =>
            encodeURIComponent(typeof window !== 'undefined' ? window.location.href : '/');

        const goToSignIn = () => {
            window.location.href = `${AUTH_ORIGIN}/signin?redirect_to=${redirectTo()}`;
        };
        const goToSignUp = () => {
            window.location.href = `${AUTH_ORIGIN}/join?redirect_to=${redirectTo()}`;
        };

        return (
            <div className="flex items-center justify-center gap-4 py-1.5">
                <button type="button" onClick={goToSignIn} className={navLinkClass}>Log In</button>
                {sep}
                <button type="button" onClick={goToSignUp} className={navLinkClass}>Sign Up</button>
            </div>
        );
    }

    const isBusiness = user?.user_type === 'BUSINESS' || user?.user_type === 'VENUE';
    const profileIncomplete = isBusiness && !user?.business_name;

    async function handleSignOut() {
        await logout();
        router.push('/');
    }

    return (
        <div className="flex items-center justify-center gap-4 py-1.5">
            <Link
                href={isOnHome ? '/profile' : '/'}
                className="relative text-[11px] uppercase tracking-widest no-underline hover:text-[var(--color-accent)] transition-colors"
            >
                {isOnHome ? 'Profile' : 'Home'}
                {isOnHome && profileIncomplete && (
                    <span
                        aria-label="Profile incomplete"
                        className="absolute -top-1 -right-2 w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]"
                    />
                )}
            </Link>
            {isBusiness && (
                <>
                    <span className="text-[var(--color-border-light)] text-xs" aria-hidden="true">/</span>
                    <Link
                        href="/dashboard"
                        className="text-[11px] uppercase tracking-widest no-underline hover:text-[var(--color-accent)] transition-colors"
                    >
                        Dashboard
                    </Link>
                </>
            )}
            <span className="text-[var(--color-border-light)] text-xs" aria-hidden="true">/</span>
            <button
                onClick={handleSignOut}
                className="text-[11px] uppercase tracking-widest bg-transparent border-none cursor-pointer p-0 hover:text-[var(--color-accent)] transition-colors"
            >
                Sign Out
            </button>
        </div>
    );
}
