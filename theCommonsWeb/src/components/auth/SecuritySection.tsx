'use client';

import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

const HEADING =
    'text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4';

export function SecuritySection() {
    const { user, setPassword } = useAuth();
    const [password, setPasswordValue] = useState('');
    const [confirm, setConfirm] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);
    const [saving, setSaving] = useState(false);

    if (!user) return null;

    if (user.hasPassword) {
        return (
            <section id="security" className="mb-10">
                <h2 className={HEADING}>Security</h2>
                <p className="text-sm text-[var(--color-text-muted)]">
                    Your account is secured with a password.
                </p>
            </section>
        );
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        if (password.length < 8) {
            setError('Password must be at least 8 characters.');
            return;
        }
        if (password !== confirm) {
            setError('Passwords do not match.');
            return;
        }
        setSaving(true);
        try {
            await setPassword(password);
            setDone(true);
            setPasswordValue('');
            setConfirm('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Could not set password.');
        } finally {
            setSaving(false);
        }
    }

    return (
        <section id="security" className="mb-10">
            <h2 className={HEADING}>Security</h2>
            <p className="text-sm text-[var(--color-text-muted)] mb-4">
                Your account has no password yet — anyone with your email can sign in. Set one to
                keep it yours.
            </p>
            {done && (
                <p className="text-sm mb-4 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                    Password set. Your account is now secured.
                </p>
            )}
            {error && (
                <p className="text-sm text-[var(--color-accent)] mb-4 border border-[var(--color-accent)] px-3 py-2">
                    {error}
                </p>
            )}
            <form onSubmit={submit} className="space-y-4 max-w-sm">
                <Input
                    label="Password"
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={e => setPasswordValue(e.target.value)}
                />
                <Input
                    label="Confirm Password"
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                />
                <Button type="submit" variant="primary" disabled={saving}>
                    {saving ? 'Saving…' : 'Set Password'}
                </Button>
            </form>
        </section>
    );
}
