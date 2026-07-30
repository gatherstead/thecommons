'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { resolveRedirect } from '../../../lib/redirect-allowlist';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import { PortalShell } from '../PortalShell';

export function SignInForm() {
    const searchParams = useSearchParams();
    const { login, isAuthenticated, isInitializing } = useAuth();

    const redirectTo = searchParams.get('redirect_to');

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const redirected = useRef(false);
    useEffect(() => {
        if (!isInitializing && isAuthenticated && !redirected.current) {
            redirected.current = true;
            window.location.href = resolveRedirect(redirectTo);
        }
    }, [isAuthenticated, isInitializing, redirectTo]);

    async function submitPassword(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            await login({ email: email.trim(), password });
            window.location.href = resolveRedirect(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Incorrect email or password.');
        } finally {
            setIsLoading(false);
        }
    }

    return (
        <PortalShell
            activeTab="signin"
            heading="Sign In"
            subheading="Welcome back — enter your details to continue."
        >
            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <form onSubmit={submitPassword} className="space-y-6">
                <Input
                    label="Email"
                    type="email"
                    autoComplete="email"
                    required
                    autoFocus
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                />
                <Input
                    label="Password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />
                <div className="flex justify-end items-center pt-2">
                    <Button type="submit" variant="primary" disabled={isLoading}>
                        {isLoading ? 'Please wait…' : 'Sign In'}
                    </Button>
                </div>
            </form>
        </PortalShell>
    );
}
