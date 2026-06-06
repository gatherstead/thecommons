'use client';

import { useEffect } from 'react';

/**
 * Better Auth redirects here after Google OAuth completes.
 * Notifies the parent window then closes itself.
 */
export default function GooglePopupCompletePage() {
    useEffect(() => {
        if (window.opener) {
            window.opener.postMessage(
                { type: 'google-auth-complete' },
                window.location.origin,
            );
            window.close();
        } else {
            // Opened directly (not as a popup) — redirect home.
            window.location.href = '/';
        }
    }, []);

    return (
        <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)]">
            <p className="text-sm font-[var(--font-body)] text-[var(--color-text-muted)]">
                Signed in — closing window…
            </p>
        </div>
    );
}
