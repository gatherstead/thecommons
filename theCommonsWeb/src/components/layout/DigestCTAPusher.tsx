'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useMessageStack } from '../../hooks/useMessageStack';
import { getProfile, type EmailPreference } from '../../services/profileService';

const DIGEST_HEADING = 'Get the Weekly Digest';
const DIGEST_SUBHEADING = "Enter your email — we'll send local events to your inbox each week.";

export const DIGEST_SIGNUP_HREF =
    `/auth/signup?intent=digest&type=local` +
    `&heading=${encodeURIComponent(DIGEST_HEADING)}` +
    `&subheading=${encodeURIComponent(DIGEST_SUBHEADING)}`;

interface DigestCTAPusherProps {
    delaySeconds?: number;
}

export function DigestCTAPusher({ delaySeconds = 15 }: DigestCTAPusherProps) {
    const { isAuthenticated, isInitializing, user, token } = useAuth();
    const { push } = useMessageStack();
    const [ready, setReady] = useState(delaySeconds === 0);
    const [emailPref, setEmailPref] = useState<EmailPreference | null>(null);

    useEffect(() => {
        if (delaySeconds === 0) return;
        const id = setTimeout(() => setReady(true), delaySeconds * 1000);
        return () => clearTimeout(id);
    }, [delaySeconds]);

    useEffect(() => {
        if (!isAuthenticated || !token) return;
        getProfile(token)
            .then((p) => setEmailPref(p.email_preference))
            .catch(() => {});
    }, [isAuthenticated, token]);

    useEffect(() => {
        if (isInitializing || !ready) return;

        // Business/venue users don't need the digest nudge
        if (isAuthenticated && user && (user.user_type === 'BUSINESS' || user.user_type === 'VENUE')) return;

        // Authenticated and already subscribed — nothing to push
        if (isAuthenticated && (emailPref === 'WEEKLY' || emailPref === 'MONTHLY')) return;

        if (!isAuthenticated) {
            push({
                id: 'digest-cta',
                content: (
                    <p className="text-xs sm:text-sm text-[var(--color-text-muted)] text-center">
                        Never miss a local event &mdash;{' '}
                        <Link href={DIGEST_SIGNUP_HREF} className="font-bold underline hover:no-underline">
                            get the weekly digest &rarr;
                        </Link>
                    </p>
                ),
            });
            return;
        }

        // Authenticated but not subscribed
        push({
            id: 'digest-cta',
            content: (
                <p className="text-xs sm:text-sm text-[var(--color-text-muted)] text-center">
                    You&rsquo;re not subscribed to the weekly digest.{' '}
                    <Link href="/profile" className="font-bold underline hover:no-underline">
                        Subscribe in your profile &rarr;
                    </Link>
                </p>
            ),
        });
    }, [isInitializing, isAuthenticated, user, emailPref, ready, push]);

    return null;
}
