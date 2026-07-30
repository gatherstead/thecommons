'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import { PortalShell } from '../PortalShell';

export function ForgotPasswordForm() {
    const searchParams = useSearchParams();
    const redirectTo = searchParams.get('redirect_to');

    const signInHref = redirectTo
        ? `/signin?redirect_to=${encodeURIComponent(redirectTo)}`
        : '/signin';

    const [email, setEmail] = useState('');
    const [submitted, setSubmitted] = useState(false);

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSubmitted(true);
    }

    return (
        <PortalShell heading="Forgot Password?">
            <div className="space-y-6">
                <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                    The Commons doesn&rsquo;t send password reset emails. In most cases you
                    don&rsquo;t need one — just enter your email on the Sign In page and
                    continue without a password.
                </p>

                <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
                    If your account has a password you can&rsquo;t recover, contact{' '}
                    <a
                        href="mailto:aryav@unc.edu"
                        className="underline hover:text-[var(--color-accent)]"
                    >
                        The Commons
                    </a>{' '}
                    for help.
                </p>

                <form onSubmit={handleSubmit} className="space-y-4 pt-2 border-t border-[var(--color-border)]">
                    <Input
                        label="Email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        placeholder="you@example.com"
                    />

                    {submitted && (
                        <div
                            className="p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                            role="status"
                        >
                            There&rsquo;s no password to reset — head to Sign In and enter
                            this email to continue without one.
                        </div>
                    )}

                    <div className="flex justify-between items-center pt-2">
                        <Button type="submit" variant="secondary" size="sm">
                            Check My Options
                        </Button>
                        <Link
                            href={signInHref}
                            className="font-[var(--font-sans)] cursor-pointer tracking-wide uppercase text-xs font-bold bg-[var(--color-text)] text-[var(--color-bg)] border-2 border-[var(--color-text)] hover:bg-[var(--color-accent)] hover:border-[var(--color-accent)] px-4 py-2.5 inline-block text-center focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                        >
                            Back to Sign In
                        </Link>
                    </div>
                </form>
            </div>
        </PortalShell>
    );
}
