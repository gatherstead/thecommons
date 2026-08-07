'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { authClient } from '../../../lib/auth-client';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';

export function ForgotPasswordForm() {
    const searchParams = useSearchParams();
    const redirectTo = searchParams.get('redirect_to');

    const signInHref = redirectTo
        ? `/signin?redirect_to=${encodeURIComponent(redirectTo)}`
        : '/signin';

    const [email, setEmail] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setIsLoading(true);
        try {
            await authClient.requestPasswordReset({
                email: email.trim(),
                redirectTo: '/reset-password',
            });
        } catch {
            // Swallow — the confirmation message stays neutral either way so
            // we never reveal whether an account exists for this email.
        } finally {
            setIsLoading(false);
            setSubmitted(true);
        }
    }

    return (
        <div className="space-y-6">
            <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                Enter your account email and we&rsquo;ll send you a link to set a new
                password.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4 pt-2 border-t border-[var(--color-border)]">
                <Input
                    label="Email"
                    type="email"
                    autoComplete="email"
                    required
                    autoFocus
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                />

                {submitted && (
                    <div
                        className="p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                        role="status"
                    >
                        If that email exists in our system, we&rsquo;ve sent a reset link.
                    </div>
                )}

                <div className="pt-2">
                    <Button
                        type="submit"
                        variant="primary"
                        className="portal-submit"
                        disabled={isLoading}
                    >
                        {isLoading ? 'Sending…' : 'Send Reset Link'}
                    </Button>
                    <p className="mt-4 text-sm italic text-[var(--color-text-muted)]">
                        <Link href={signInHref} className="portal-link">
                            Back to sign in
                        </Link>
                    </p>
                </div>
            </form>
        </div>
    );
}
