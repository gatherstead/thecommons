'use client';

import { useEffect, useRef, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import { useAuth } from '../../hooks/useAuth';
import type { UserType } from '../../models/authModels';

type Mode = 'login' | 'signup';

interface AuthModalProps {
    isOpen: boolean;
    onClose: () => void;
    onAuthenticated?: () => void;
    initialMode?: Mode;
    intro?: string;
}

export function AuthModal({
    isOpen,
    onClose,
    onAuthenticated,
    initialMode = 'signup',
    intro,
}: AuthModalProps) {
    const { login, signup, refreshSession } = useAuth();

    const [mode, setMode] = useState<Mode>(initialMode);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [businessName, setBusinessName] = useState('');
    const [userType, setUserType] = useState<UserType>('BUSINESS');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const popupRef = useRef<Window | null>(null);

    useEffect(() => {
        if (!isOpen) return;
        setMode(initialMode);
        setEmail('');
        setPassword('');
        setBusinessName('');
        setUserType('BUSINESS');
        setError(null);
        setIsLoading(false);
    }, [isOpen, initialMode]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            if (mode === 'signup') {
                await signup({
                    email: email.trim(),
                    password,
                    business_name: businessName.trim(),
                    user_type: userType,
                });
            } else {
                await login({ email: email.trim(), password });
            }
            onAuthenticated?.();
            onClose();
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : 'Something went wrong. Please try again.';
            setError(message);
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogle = () => {
        setError(null);

        if (popupRef.current && !popupRef.current.closed) {
            popupRef.current.focus();
            return;
        }

        const popup = window.open(
            '/auth/google-popup',
            'google-auth',
            'popup,width=520,height=620,left=200,top=100',
        );
        if (!popup) {
            setError('Pop-up blocked — please allow pop-ups for this site and try again.');
            return;
        }
        popupRef.current = popup;

        const handleMessage = async (event: MessageEvent) => {
            if (event.origin !== window.location.origin) return;
            if (event.data?.type !== 'google-auth-complete') return;
            window.removeEventListener('message', handleMessage);
            clearInterval(pollClosed);
            popupRef.current = null;
            try {
                await refreshSession();
                onAuthenticated?.();
                onClose();
            } catch (err: unknown) {
                const message = err instanceof Error ? err.message : 'Sign-in failed — please try again.';
                setError(message);
            }
        };

        window.addEventListener('message', handleMessage);

        const pollClosed = setInterval(() => {
            if (popup.closed) {
                clearInterval(pollClosed);
                window.removeEventListener('message', handleMessage);
                popupRef.current = null;
            }
        }, 500);
    };

    const title = mode === 'signup' ? 'Create Business Account' : 'Sign In';
    const submitLabel = mode === 'signup' ? 'Create Account' : 'Sign In';
    const switchPrompt = mode === 'signup' ? 'Already have an account?' : 'Need an account?';
    const switchAction = mode === 'signup' ? 'Sign in' : 'Sign up';

    return (
        <Modal isOpen={isOpen} onClose={onClose} title={title}>
            {intro && (
                <p className="mb-4 text-sm italic text-[var(--color-text-muted)] leading-snug">
                    {intro}
                </p>
            )}

            {error && (
                <div
                    className="mb-4 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
                {mode === 'signup' && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Input
                            label="Business / Venue Name"
                            type="text"
                            required
                            value={businessName}
                            onChange={e => setBusinessName(e.target.value)}
                        />
                        <Select
                            label="Account Type"
                            value={userType}
                            onChange={e => setUserType(e.target.value as UserType)}
                        >
                            <option value="BUSINESS">Business</option>
                            <option value="VENUE">Venue</option>
                            <option value="LOCAL">Local</option>
                        </Select>
                    </div>
                )}

                <Input
                    label="Email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                />

                <Input
                    label="Password"
                    type="password"
                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                    required
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                />

                <div className="pt-4 border-t border-[var(--color-border-light)] flex flex-col-reverse md:flex-row md:justify-between md:items-center gap-3">
                    <button
                        type="button"
                        onClick={() => {
                            setError(null);
                            setMode(mode === 'signup' ? 'login' : 'signup');
                        }}
                        className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0 text-left"
                    >
                        {switchPrompt} <span className="font-bold">{switchAction}</span>
                    </button>

                    <div className="flex gap-3 md:justify-end">
                        <Button type="button" variant="secondary" onClick={onClose}>
                            Cancel
                        </Button>
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : submitLabel}
                        </Button>
                    </div>
                </div>
            </form>

            <div className="my-5 flex items-center gap-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <span className="flex-1 border-t border-[var(--color-border-light)]" />
                <span>or</span>
                <span className="flex-1 border-t border-[var(--color-border-light)]" />
            </div>

            <button
                type="button"
                onClick={handleGoogle}
                className="w-full flex items-center justify-center gap-3 border border-[var(--color-border)] py-3 px-4 text-xs uppercase tracking-wider font-bold hover:bg-[var(--color-bg-alt)] transition-colors cursor-pointer bg-transparent"
            >
                <GoogleIcon />
                Continue with Google
            </button>

            <p className="mt-4 text-[10px] text-[var(--color-text-muted)] text-center uppercase tracking-wider">
                Your account is used only to post and manage your events.
            </p>
        </Modal>
    );
}

function GoogleIcon() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
    );
}
