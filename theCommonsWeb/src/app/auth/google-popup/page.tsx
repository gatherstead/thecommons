'use client';

import { useEffect } from 'react';
import { authClient } from '../../../lib/auth-client';

/**
 * Loaded inside a popup window. Immediately kicks off the Google OAuth redirect
 * so the parent window never navigates away.
 */
export default function GooglePopupPage() {
    useEffect(() => {
        authClient.signIn.social({
            provider: 'google',
            callbackURL: '/auth/google-popup/complete',
        });
    }, []);

    return (
        <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)]">
            <p className="text-sm font-[var(--font-body)] text-[var(--color-text-muted)]">
                Redirecting to Google…
            </p>
        </div>
    );
}
