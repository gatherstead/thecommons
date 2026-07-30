'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { resolveRedirect } from '../../../lib/redirect-allowlist';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import { PortalShell } from '../PortalShell';

export function SetPasswordForm() {
    const searchParams = useSearchParams();
    const { setPassword, isAuthenticated, isInitializing } = useAuth();

    const redirectTo = searchParams.get('redirect_to');

    const [password, setPasswordValue] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [done, setDone] = useState(false);

    const bounced = useRef(false);
    useEffect(() => {
        if (!isInitializing && !isAuthenticated && !bounced.current) {
            bounced.current = true;
            window.location.href = `/signin?redirect_to=${encodeURIComponent(window.location.href)}`;
        }
    }, [isAuthenticated, isInitializing]);

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            await setPassword(password);
            if (redirectTo) {
                window.location.href = resolveRedirect(redirectTo);
            } else {
                setDone(true);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Could not set password.');
        } finally {
            setIsLoading(false);
        }
    }

    if (isInitializing || !isAuthenticated) {
        return null;
    }

    return (
        <PortalShell
            heading="Secure Your Account"
            subheading="Set a password so you can sign in without an email link."
        >
            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            {done ? (
                <p className="text-sm border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                    Password set. Your account is secured.
                </p>
            ) : (
                <form onSubmit={submit} className="space-y-6">
                    <Input
                        label="Password"
                        type="password"
                        autoComplete="new-password"
                        required
                        minLength={8}
                        autoFocus
                        value={password}
                        onChange={e => setPasswordValue(e.target.value)}
                    />
                    <div className="flex justify-end items-center pt-2">
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Set Password'}
                        </Button>
                    </div>
                </form>
            )}
        </PortalShell>
    );
}
