'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { authClient } from '../../lib/auth-client';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';

const MIN_PASSWORD_LENGTH = 8;

// Public, login-free page reached via the reset link in the password-reset
// email (see sendResetPassword in lib/auth.ts). The token in the query
// string IS the credential — no session/auth gate here.
export function ResetPasswordForm() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [done, setDone] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);

        if (!token) {
            setError('This reset link is missing its token. Request a new one from the forgot password page.');
            return;
        }
        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
            return;
        }
        if (password !== confirm) {
            setError('Passwords do not match.');
            return;
        }

        setIsLoading(true);
        try {
            const { error: resetError } = await authClient.resetPassword({
                newPassword: password,
                token,
            });
            if (resetError) {
                throw new Error(resetError.message ?? 'This reset link is invalid or has expired.');
            }
            setDone(true);
            window.location.href = '/signin';
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : 'This reset link is invalid or has expired. Request a new one from the forgot password page.',
            );
        } finally {
            setIsLoading(false);
        }
    }

    return (
        <main id="main-content" className="max-w-[480px] mx-auto px-4 py-12">
            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-1"
                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                >
                    Reset Password
                </h1>
                <p className="text-sm italic text-[var(--color-text-muted)]">
                    Choose a new password for your account.
                </p>
            </header>

            {!token ? (
                <div className="border-2 border-[var(--color-border)] p-6 text-center">
                    <p className="font-bold mb-2">Missing reset link.</p>
                    <p className="text-sm text-[var(--color-text-muted)] mb-4">
                        Use the link from your password reset email, or request a new one below.
                    </p>
                    <Link
                        href="/forgot-password"
                        className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors"
                    >
                        &larr; Request a Reset Link
                    </Link>
                </div>
            ) : (
                <>
                    {error && (
                        <div
                            className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                            role="alert"
                        >
                            {error}
                        </div>
                    )}
                    {done && (
                        <div
                            className="mb-6 p-2 border border-[var(--color-border)] bg-[var(--color-bg-alt)] text-sm"
                            role="status"
                        >
                            Password updated. Redirecting to sign in&hellip;
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <Input
                            label="New Password"
                            type="password"
                            autoComplete="new-password"
                            required
                            autoFocus
                            minLength={MIN_PASSWORD_LENGTH}
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                        />
                        <Input
                            label="Confirm New Password"
                            type="password"
                            autoComplete="new-password"
                            required
                            minLength={MIN_PASSWORD_LENGTH}
                            value={confirm}
                            onChange={e => setConfirm(e.target.value)}
                        />
                        <div className="flex justify-end items-center pt-2">
                            <Button type="submit" variant="primary" disabled={isLoading}>
                                {isLoading ? 'Please wait…' : 'Set New Password'}
                            </Button>
                        </div>
                    </form>
                </>
            )}
        </main>
    );
}
