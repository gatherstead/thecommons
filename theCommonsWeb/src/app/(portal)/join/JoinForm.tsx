'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { resolveRedirect } from '@/lib/redirect-allowlist';
import type { UserType } from '@/models/authModels';
import { PortalShell, PortalField, PortalSubmit } from '../PortalShell';

const USER_TYPE_OPTIONS: { value: UserType; label: string }[] = [
    { value: 'LOCAL', label: 'Local' },
    { value: 'BUSINESS', label: 'Business' },
    { value: 'VENUE', label: 'Venue' },
];

export function JoinForm() {
    const searchParams = useSearchParams();
    const { enter, login, isAuthenticated, isInitializing } = useAuth();

    const redirectParam = searchParams.get('redirect_to');

    const [step, setStep] = useState<'email' | 'password'>('email');
    const [userType, setUserType] = useState<UserType>('LOCAL');
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const isBusinessOrVenue = userType === 'BUSINESS' || userType === 'VENUE';

    const redirected = useRef(false);
    useEffect(() => {
        if (!isInitializing && isAuthenticated && !redirected.current) {
            redirected.current = true;
            window.location.href = resolveRedirect(redirectParam);
        }
    }, [isAuthenticated, isInitializing, redirectParam]);

    async function submitEmail(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            const result = await enter({
                email: email.trim(),
                user_type: userType,
                name: isBusinessOrVenue ? name.trim() : undefined,
            });
            if (result.requiresPassword) {
                setStep('password');
                return;
            }
            window.location.href = resolveRedirect(redirectParam);
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
            window.location.href = resolveRedirect(redirectParam);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Incorrect password.');
            setIsLoading(false);
        }
    }

    return (
        <PortalShell activeTab="join">
            <p className="text-sm italic text-[var(--color-text-muted)] mb-6">
                {step === 'email'
                    ? 'No password required — just tell us your email.'
                    : 'This account is secured with a password.'}
            </p>

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
                                    className={`flex-1 text-xs uppercase tracking-wider font-bold py-2 border cursor-pointer transition-colors ${
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

                    {isBusinessOrVenue && (
                        <PortalField
                            label={userType === 'VENUE' ? 'Venue Name' : 'Business Name'}
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                        />
                    )}

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

                    <PortalSubmit type="submit" disabled={isLoading}>
                        {isLoading ? 'Please wait…' : 'Continue'}
                    </PortalSubmit>
                </form>
            )}

            {step === 'password' && (
                <form onSubmit={submitPassword} className="space-y-6">
                    <p className="text-sm text-[var(--color-text-muted)]">
                        Enter the password for <span className="font-bold">{email.trim()}</span>.
                    </p>
                    <PortalField
                        label="Password"
                        type="password"
                        autoComplete="current-password"
                        required
                        autoFocus
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                    />
                    <PortalSubmit type="submit" disabled={isLoading}>
                        {isLoading ? 'Please wait…' : 'Sign In'}
                    </PortalSubmit>
                    <button
                        type="button"
                        onClick={() => { setPassword(''); setStep('email'); }}
                        className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-text)] underline bg-transparent border-none cursor-pointer p-0"
                    >
                        &larr; Use a different email
                    </button>
                </form>
            )}
        </PortalShell>
    );
}
