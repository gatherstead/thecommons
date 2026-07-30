'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { resolveRedirect } from '../../../lib/redirect-allowlist';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import { PortalShell } from '../PortalShell';
import type { UserType } from '../../../models/authModels';

const USER_TYPE_OPTIONS: { value: UserType; label: string }[] = [
    { value: 'LOCAL', label: 'Local' },
    { value: 'BUSINESS', label: 'Business' },
    { value: 'VENUE', label: 'Venue' },
];

export function JoinForm() {
    const searchParams = useSearchParams();
    const { enter, login, isAuthenticated, isInitializing } = useAuth();

    const redirectTo = searchParams.get('redirect_to');

    const [step, setStep] = useState<'email' | 'password'>('email');
    const [userType, setUserType] = useState<UserType>('LOCAL');
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

    async function submitEmail(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            const result = await enter({ email: email.trim(), user_type: userType });
            if (result.requiresPassword) {
                setStep('password');
                return;
            }
            window.location.href = resolveRedirect(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Something went wrong.');
        } finally {
            setIsLoading(false);
        }
    }

    async function submitPassword(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            await login({ email: email.trim(), password });
            window.location.href = resolveRedirect(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Incorrect password.');
        } finally {
            setIsLoading(false);
        }
    }

    return (
        <PortalShell
            activeTab="join"
            heading="Create Account"
            subheading="No password required — just your email to start."
        >
            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            {step === 'email' && (
                <form onSubmit={submitEmail} className="space-y-6">
                    <div>
                        <span className="block text-xs uppercase tracking-wider font-bold mb-1">
                            I am a…
                        </span>
                        <div className="flex gap-2">
                            {USER_TYPE_OPTIONS.map(opt => (
                                <button
                                    key={opt.value}
                                    type="button"
                                    onClick={() => setUserType(opt.value)}
                                    aria-pressed={userType === opt.value}
                                    className={`flex-1 text-center border py-2 px-2 text-xs uppercase tracking-wider font-bold cursor-pointer ${
                                        userType === opt.value
                                            ? 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]'
                                            : 'bg-transparent border-[var(--color-border)] hover:bg-[var(--color-bg-alt)]'
                                    }`}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <Input
                        label="Email"
                        type="email"
                        autoComplete="email"
                        required
                        autoFocus
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                    />
                    <div className="flex justify-end items-center pt-2">
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Continue'}
                        </Button>
                    </div>
                </form>
            )}

            {step === 'password' && (
                <form onSubmit={submitPassword} className="space-y-6">
                    <p className="text-sm text-[var(--color-text-muted)]">
                        This account is secured with a password. Enter it to sign in as{' '}
                        <span className="font-bold">{email.trim()}</span>.
                    </p>
                    <Input
                        label="Password"
                        type="password"
                        autoComplete="current-password"
                        required
                        autoFocus
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                    />
                    <div className="flex justify-between items-center pt-2">
                        <button
                            type="button"
                            onClick={() => { setPassword(''); setError(null); setStep('email'); }}
                            className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0"
                        >
                            &larr; Use a different email
                        </button>
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Sign In'}
                        </Button>
                    </div>
                </form>
            )}
        </PortalShell>
    );
}
