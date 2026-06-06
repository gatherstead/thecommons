'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useMessageStack } from '../../hooks/useMessageStack';

export function AccountBannerPusher() {
    const { isAuthenticated, isInitializing, user } = useAuth();
    const { push } = useMessageStack();

    useEffect(() => {
        if (isInitializing || !isAuthenticated || !user || user.hasPassword) return;
        push({
            id: 'account-set-password',
            variant: 'accent',
            content: (
                <p className="text-xs sm:text-sm text-[var(--color-accent)] font-bold text-center">
                    Your account isn&rsquo;t secured with a password &mdash; anyone with your email can log in.{' '}
                    <Link href="/profile#security" className="underline hover:no-underline">
                        Set a password &rarr;
                    </Link>
                </p>
            ),
        });
    }, [isInitializing, isAuthenticated, user, push]);

    return null;
}
