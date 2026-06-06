'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '../../hooks/useAuth';

export function HeaderAuthNav() {
    const { isAuthenticated, isInitializing, user, logout } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const isOnHome = pathname === '/';
    const isOnLogin = pathname === '/auth/login';
    const isOnSignup = pathname === '/auth/signup';

    if (isInitializing) return null;

    if (!isAuthenticated) {
        const navLinkClass = "text-[11px] uppercase tracking-widest no-underline hover:text-[var(--color-accent)] transition-colors";
        const sep = <span className="text-[var(--color-border-light)] text-xs" aria-hidden="true">/</span>;
        const next = encodeURIComponent(pathname || '/');

        let left: React.ReactNode;
        let right: React.ReactNode;

        if (isOnLogin) {
            left = <Link href="/" className={navLinkClass}>Home</Link>;
            right = <Link href="/auth/signup" className={navLinkClass}>Sign Up</Link>;
        } else if (isOnSignup) {
            left = <Link href="/auth/login" className={navLinkClass}>Log In</Link>;
            right = <Link href="/" className={navLinkClass}>Home</Link>;
        } else {
            left = <Link href={`/auth/login?redirect=${next}`} className={navLinkClass}>Log In</Link>;
            right = <Link href={`/auth/signup?redirect=${next}`} className={navLinkClass}>Sign Up</Link>;
        }

        return (
            <div className="flex items-center justify-center gap-4 py-1.5">
                {left}{sep}{right}
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
