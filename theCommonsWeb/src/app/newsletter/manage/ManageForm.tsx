'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button } from '../../../components/ui/Button';
import {
    getSubscription,
    updateSubscription,
    type ManageFrequency,
    type NewsletterManageState,
} from '../../../services/newsletterService';

const FREQUENCY_OPTIONS: { value: ManageFrequency; label: string; description: string }[] = [
    { value: 'WEEKLY', label: 'Weekly', description: 'Every Monday morning' },
    { value: 'MONTHLY', label: 'Monthly', description: 'First of each month' },
    { value: 'NEVER', label: 'Unsubscribe', description: "I don't want the digest anymore" },
];

function currentSelection(sub: NewsletterManageState): ManageFrequency {
    return sub.is_active ? sub.frequency : 'NEVER';
}

// Login-free manage page — reached via the token link in the welcome/digest
// emails (send_newsletter_welcome / send_digest). No auth gate: the token in
// the query string IS the credential.
export function ManageForm() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [subscription, setSubscription] = useState<NewsletterManageState | null>(null);
    const [selected, setSelected] = useState<ManageFrequency | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [saved, setSaved] = useState(false);

    const load = useCallback(async () => {
        if (!token) {
            setIsLoading(false);
            return;
        }
        setIsLoading(true);
        setError(null);
        setNotFound(false);
        try {
            const data = await getSubscription(token);
            setSubscription(data);
            setSelected(currentSelection(data));
        } catch (err) {
            if (err instanceof Error && err.message === 'NOT_FOUND') {
                setNotFound(true);
            } else {
                setError('Could not load your subscription. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    useEffect(() => { load(); }, [load]);

    async function save() {
        if (!token || !selected) return;
        setIsSaving(true);
        setError(null);
        setSaved(false);
        try {
            const updated = await updateSubscription(token, { frequency: selected });
            setSubscription(updated);
            setSelected(currentSelection(updated));
            setSaved(true);
        } catch (err) {
            setError(err instanceof Error && err.message !== 'NOT_FOUND'
                ? err.message
                : 'Could not save your changes. Please try again.');
        } finally {
            setIsSaving(false);
        }
    }

    const isDirty = subscription !== null && selected !== null && selected !== currentSelection(subscription);

    return (
        <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-1"
                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                >
                    Manage Newsletter
                </h1>
                {subscription && (
                    <p className="text-sm italic text-[var(--color-text-muted)]">{subscription.email}</p>
                )}
            </header>

            {!token || notFound ? (
                <div className="border-2 border-[var(--color-border)] p-6 text-center">
                    <p className="font-bold mb-2">
                        {token ? "We couldn't find that subscription." : 'Missing manage link.'}
                    </p>
                    <p className="text-sm text-[var(--color-text-muted)] mb-4">
                        {token
                            ? 'This link may have expired or already been used. You can subscribe again from the homepage footer.'
                            : 'Use the link from your subscription confirmation or digest email to manage your preferences.'}
                    </p>
                    <Link href="/" className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors">
                        &larr; Return to Feed
                    </Link>
                </div>
            ) : isLoading ? (
                <div className="space-y-3">
                    {[1, 2, 3].map(i => <div key={i} className="skeleton-block h-12 w-full" />)}
                </div>
            ) : subscription && selected ? (
                <>
                    {error && (
                        <p className="text-sm text-[var(--color-accent)] mb-6 border border-[var(--color-accent)] px-3 py-2" role="alert">
                            {error}
                        </p>
                    )}
                    {saved && (
                        <p className="text-sm mb-6 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]" role="status">
                            {selected === 'NEVER' ? "You've been unsubscribed." : 'Preferences saved.'}
                        </p>
                    )}

                    <section className="mb-8">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                            Frequency
                        </h2>
                        <fieldset className="space-y-2">
                            <legend className="sr-only">Digest frequency</legend>
                            {FREQUENCY_OPTIONS.map(opt => (
                                <label key={opt.value} className="flex items-start gap-3 group cursor-pointer">
                                    <input
                                        type="radio"
                                        name="frequency"
                                        value={opt.value}
                                        checked={selected === opt.value}
                                        onChange={() => setSelected(opt.value)}
                                        className="mt-1 accent-[var(--color-accent)] shrink-0"
                                    />
                                    <span>
                                        <span className="text-sm font-bold transition-colors group-hover:text-[var(--color-accent)]">
                                            {opt.label}
                                        </span>
                                        <span className="text-xs text-[var(--color-text-muted)] ml-2">
                                            {opt.description}
                                        </span>
                                    </span>
                                </label>
                            ))}
                        </fieldset>
                    </section>

                    <div className="flex items-center gap-4">
                        <Button variant="primary" onClick={save} disabled={!isDirty || isSaving}>
                            {isSaving ? 'Saving…' : 'Save Changes'}
                        </Button>
                        {isDirty && !isSaving && (
                            <span className="text-xs text-[var(--color-text-muted)] italic">Unsaved changes</span>
                        )}
                    </div>
                </>
            ) : null}
        </main>
    );
}
