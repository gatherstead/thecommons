'use client';

import { useEffect, useState } from 'react';
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
    const { login, signup } = useAuth();

    const [mode, setMode] = useState<Mode>(initialMode);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [businessName, setBusinessName] = useState('');
    const [userType, setUserType] = useState<UserType>('BUSINESS');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

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
        } catch (err: any) {
            setError(err?.message || 'Something went wrong. Please try again.');
        } finally {
            setIsLoading(false);
        }
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
        </Modal>
    );
}
