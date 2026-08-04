'use client';

import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { authClient } from '../../lib/auth-client';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

const HEADING =
    'text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4';

const MIN_PASSWORD_LENGTH = 8;

export function SecuritySection() {
    const { user } = useAuth();

    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    if (!user) return null;

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setSuccess(false);

        if (newPassword.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
            return;
        }
        if (newPassword !== confirm) {
            setError('Passwords do not match.');
            return;
        }

        setIsLoading(true);
        try {
            const { error: changeError } = await authClient.changePassword({
                currentPassword,
                newPassword,
                revokeOtherSessions: true,
            });
            if (changeError) {
                throw new Error(changeError.message ?? 'Your current password is incorrect.');
            }
            setSuccess(true);
            setCurrentPassword('');
            setNewPassword('');
            setConfirm('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Your current password is incorrect.');
        } finally {
            setIsLoading(false);
        }
    }

    return (
        <section id="security" className="mb-10">
            <h2 className={HEADING}>Security</h2>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">
                Change the password used to sign in to your account.
            </p>

            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}
            {success && (
                <div
                    className="mb-6 p-2 border border-[var(--color-border)] bg-[var(--color-bg-alt)] text-sm"
                    role="status"
                >
                    Password updated.
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6 max-w-[480px]">
                <Input
                    label="Current Password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={currentPassword}
                    onChange={e => setCurrentPassword(e.target.value)}
                />
                <Input
                    label="New Password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={MIN_PASSWORD_LENGTH}
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
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
                        {isLoading ? 'Please wait…' : 'Change Password'}
                    </Button>
                </div>
            </form>
        </section>
    );
}
