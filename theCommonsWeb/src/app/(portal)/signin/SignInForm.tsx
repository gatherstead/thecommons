'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { resolveRedirect } from '../../../lib/redirect-allowlist';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';

export function SignInForm({
    email,
    onEmailChange,
    autoFocus,
}: {
    email: string;
    onEmailChange: (value: string) => void;
    autoFocus?: boolean;
}) {
    const searchParams = useSearchParams();
    const { login, isAuthenticated, isInitializing } = useAuth();

    const redirectTo = searchParams.get('redirect_to');
    const forgotPasswordHref = redirectTo
        ? `/forgot-password?redirect_to=${encodeURIComponent(redirectTo)}`
        : '/forgot-password';

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
        <>
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
                    autoFocus={autoFocus}
                    placeholder="you@saxapahaw.com"
                    value={email}
                    onChange={e => onEmailChange(e.target.value)}
                />
                <Input
                    label="Password"
                    type="password"
                    autoComplete="current-password"
                    required
                    placeholder="••••••"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />
                <div className="pt-2">
                    <Button
                        type="submit"
                        variant="primary"
                        className="portal-submit"
                        disabled={isLoading}
                    >
                        {isLoading ? 'Please wait…' : 'Sign In'}
                    </Button>
                    <p className="mt-4 text-sm italic text-[var(--color-text-muted)]">
                        <Link href={forgotPasswordHref} className="portal-link">
                            Forgot your password?
                        </Link>
                    </p>
                </div>
            </form>
        </>
    );
}
