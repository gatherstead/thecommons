'use client';

// Google sign-in is temporarily disabled — revisit later. The OAuth flow
// returned `invalid_code` and bypassed user-type selection during signup, so
// the redirect below is commented out and this page is unreachable for now.
//
// import { useEffect } from 'react';
// import { authClient } from '../../../lib/auth-client';

/**
 * Loaded inside a popup window. (Disabled) Would kick off the Google OAuth
 * redirect so the parent window never navigates away.
 */
export default function GooglePopupPage() {
    // useEffect(() => {
    //     authClient.signIn.social({
    //         provider: 'google',
    //         callbackURL: '/auth/google-popup/complete',
    //     });
    // }, []);

    return (
        <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)]">
            <p className="text-sm font-[var(--font-body)] text-[var(--color-text-muted)]">
                Google sign-in is currently unavailable.
            </p>
        </div>
    );
}
