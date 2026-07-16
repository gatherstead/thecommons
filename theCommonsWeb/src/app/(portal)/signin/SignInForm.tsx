'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { resolveRedirect } from '@/lib/redirect-allowlist';
import { PortalShell, PortalField, PortalSubmit } from '../PortalShell';

export function SignInForm() {
    const searchParams = useSearchParams();
    const { login, isAuthenticated, isInitializing } = useAuth();

    const redirectParam = searchParams.get('redirect_to');

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const redirected = useRef(false);
    useEffect(() => {
        if (!isInitializing && isAuthenticated && !redirected.current) {
            redirected.current = true;
            window.location.href = resolveRedirect(redirectParam);
        }
    }, [isAuthenticated, isInitializing, redirectParam]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            await login({ email: email.trim(), password });
            window.location.href = resolveRedirect(redirectParam);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Incorrect email or password.');
            setIsLoading(false);
        }
    }

    return (
        <PortalShell activeTab="signin">
            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
                <PortalField
                    label="Email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@saxapahaw.com"
                    required
                    autoFocus
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                />
                <PortalField
                    label="Password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />
                <PortalSubmit type="submit" disabled={isLoading}>
                    {isLoading ? 'Please wait…' : 'Sign In'}
                </PortalSubmit>
                <div className="flex justify-between items-center">
                    <p className="text-sm italic text-[var(--color-text-muted)]">
                        No account?{' '}
                        <Link href="/join" className="underline hover:text-[var(--color-text)]">
                            Enter your email to get started.
                        </Link>
                    </p>
                    <Link
                        href="/forgot-password"
                        className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-text)] underline shrink-0 ml-4"
                    >
                        Forgot?
                    </Link>
                </div>
            </form>
        </PortalShell>
    );
}
