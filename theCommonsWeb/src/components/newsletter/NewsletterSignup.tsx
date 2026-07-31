'use client';

import { useState } from 'react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { subscribe, type NewsletterFrequency } from '../../services/newsletterService';

const FREQUENCY_OPTIONS: { value: NewsletterFrequency; label: string }[] = [
    { value: 'WEEKLY', label: 'Weekly' },
    { value: 'MONTHLY', label: 'Monthly' },
];

// Login-free newsletter signup. Anyone can subscribe with just an email —
// no account, no /join redirect. A manage-subscription link is emailed
// server-side on success (see events/email_service.py send_newsletter_welcome).
export function NewsletterSignup({ id }: { id?: string }) {
    const [email, setEmail] = useState('');
    const [frequency, setFrequency] = useState<NewsletterFrequency>('WEEKLY');
    const [status, setStatus] = useState<'idle' | 'loading' | 'success'>('idle');
    const [error, setError] = useState<string | null>(null);

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setStatus('loading');
        try {
            await subscribe({ email: email.trim(), frequency });
            setStatus('success');
        } catch (err) {
            setStatus('idle');
            setError(err instanceof Error ? err.message : 'Something went wrong.');
        }
    }

    if (status === 'success') {
        return (
            <div id={id} className="text-left text-xs text-(--color-text-muted) leading-relaxed">
                <p className="font-bold text-(--color-text) mb-1">You&rsquo;re on the list.</p>
                <p>Check your email for a link to manage your subscription.</p>
            </div>
        );
    }

    return (
        <form id={id} onSubmit={submit} className="text-left space-y-2.5">
            <Input
                label="Email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
            />
            <div className="flex gap-1.5" role="radiogroup" aria-label="Digest frequency">
                {FREQUENCY_OPTIONS.map(opt => (
                    <button
                        key={opt.value}
                        type="button"
                        role="radio"
                        aria-checked={frequency === opt.value}
                        onClick={() => setFrequency(opt.value)}
                        className={`flex-1 text-center border py-1 text-[10px] uppercase tracking-wider font-bold cursor-pointer transition-colors ${
                            frequency === opt.value
                                ? 'bg-(--color-text) border-(--color-text) text-(--color-bg)'
                                : 'bg-transparent border-(--color-border) hover:bg-(--color-bg-alt)'
                        }`}
                    >
                        {opt.label}
                    </button>
                ))}
            </div>
            {error && (
                <p className="text-(--color-accent) text-xs font-bold" role="alert">
                    {error}
                </p>
            )}
            <Button type="submit" variant="primary" size="sm" disabled={status === 'loading'} className="w-full">
                {status === 'loading' ? 'Subscribing…' : 'Subscribe'}
            </Button>
        </form>
    );
}
