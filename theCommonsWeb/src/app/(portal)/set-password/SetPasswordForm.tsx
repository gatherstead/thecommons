'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { PortalShell, PortalField, PortalSubmit } from '../PortalShell';
import { useAuth } from '@/hooks/useAuth';
import { resolveRedirect } from '@/lib/redirect-allowlist';

export function SetPasswordForm() {
    const searchParams = useSearchParams();
    const { isAuthenticated, isInitializing, setPassword } = useAuth();

    const redirectParam = searchParams.get('redirect_to');

    const [password, setPasswordValue] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!isInitializing && !isAuthenticated) {
            const returnPath = window.location.pathname + window.location.search;
            window.location.href = '/signin?redirect_to=' + encodeURIComponent(returnPath);
        }
    }, [isInitializing, isAuthenticated]);

    if (isInitializing || !isAuthenticated) {
        return (
            <PortalShell>
                <div className="skeleton-block h-8 w-48 mb-4" />
                <div className="skeleton-block h-4 w-full mb-2" />
            </PortalShell>
        );
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        if (password.length < 8) {
            setError('Password must be at least 8 characters.');
            return;
        }
        if (password !== confirm) {
            setError('Passwords do not match.');
            return;
        }
        setSaving(true);
        try {
            await setPassword(password);
            if (redirectParam) {
                window.location.href = resolveRedirect(redirectParam);
                return;
            }
            setDone(true);
            setPasswordValue('');
            setConfirm('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Could not set password.');
        } finally {
            setSaving(false);
        }
    }

    return (
        <PortalShell>
            <p className="text-sm italic text-[var(--color-text-muted)] mb-6">
                Secure your account with a password so you can sign in without an email link.
            </p>

            {done && (
                <p className="text-sm mb-4 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                    Password set. Your account is now secured.{' '}
                    <Link href="/" className="underline hover:text-[var(--color-accent)]">
                        Continue to The Commons
                    </Link>
                </p>
            )}

            {error && (
                <p
                    role="alert"
                    className="text-sm text-[var(--color-accent)] mb-4 border border-[var(--color-accent)] px-3 py-2"
                >
                    {error}
                </p>
            )}

            {!done && (
                <form onSubmit={submit} className="space-y-6">
                    <PortalField
                        label="Password"
                        type="password"
                        autoComplete="new-password"
                        value={password}
                        onChange={e => setPasswordValue(e.target.value)}
                    />
                    <PortalField
                        label="Confirm Password"
                        type="password"
                        autoComplete="new-password"
                        value={confirm}
                        onChange={e => setConfirm(e.target.value)}
                    />
                    <PortalSubmit type="submit" disabled={saving}>
                        {saving ? 'Saving…' : 'Set Password'}
                    </PortalSubmit>
                </form>
            )}
        </PortalShell>
    );
}
