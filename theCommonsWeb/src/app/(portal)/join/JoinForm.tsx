'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { resolveRedirect } from '../../../lib/redirect-allowlist';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import type { UserType } from '../../../models/authModels';

const USER_TYPE_OPTIONS: { value: UserType; label: string }[] = [
    { value: 'LOCAL', label: 'Local' },
    { value: 'BUSINESS', label: 'Business' },
    { value: 'VENUE', label: 'Venue' },
];

const MIN_PASSWORD_LENGTH = 8;

export function JoinForm({
    email,
    onEmailChange,
    autoFocus,
}: {
    email: string;
    onEmailChange: (value: string) => void;
    autoFocus?: boolean;
}) {
    const searchParams = useSearchParams();
    const { signup, isAuthenticated, isInitializing } = useAuth();

    const redirectTo = searchParams.get('redirect_to');

    const [userType, setUserType] = useState<UserType>('LOCAL');
    const [password, updatePassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const redirected = useRef(false);
    useEffect(() => {
        if (!isInitializing && isAuthenticated && !redirected.current) {
            redirected.current = true;
            window.location.href = resolveRedirect(redirectTo);
        }
    }, [isAuthenticated, isInitializing, redirectTo]);

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
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
            await signup({ email: email.trim(), password, user_type: userType });
            window.location.href = resolveRedirect(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Something went wrong.');
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

            <form onSubmit={submit} className="space-y-6">
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
                                className={`flex-1 text-center border py-2 px-2 text-xs uppercase tracking-wider font-bold cursor-pointer transition-colors ${
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
                    autoFocus={autoFocus}
                    placeholder="you@saxapahaw.com"
                    value={email}
                    onChange={e => onEmailChange(e.target.value)}
                />
                <Input
                    label="Password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={MIN_PASSWORD_LENGTH}
                    value={password}
                    onChange={e => updatePassword(e.target.value)}
                />
                <Input
                    label="Confirm Password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={MIN_PASSWORD_LENGTH}
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                />
                <div className="pt-2">
                    <Button
                        type="submit"
                        variant="primary"
                        className="portal-submit"
                        disabled={isLoading}
                    >
                        {isLoading ? 'Please wait…' : 'Create Account'}
                    </Button>
                </div>
            </form>
        </>
    );
}
