'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { EventPayload } from '../../models/eventsModels';
import { FILTER_TAGS, type TagId } from '../../constants/tags';
import { createEvent } from '../../services/eventService';
import { useAuth } from '../../hooks/useAuth';
import { useTowns } from '../../hooks/useTowns';
import { useCategories } from '../../hooks/useCategories';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import { Button } from '../../components/ui/Button';

// Survives the redirect to /auth: the event the user filled in before hitting the
// auth wall is stashed here and auto-submitted once they return authenticated.
const PENDING_EVENT_KEY = 'pendingEventPayload';

type Step = 'town' | 'category' | 'details' | 'done';

export default function PostEventPage() {
    const router = useRouter();
    const { token, isAuthenticated, isInitializing } = useAuth();

    const queryClient = useQueryClient();
    const [step, setStep] = useState<Step>('town');
    const [error, setError] = useState<string | null>(null);

    const towns = useTowns().data ?? [];
    const categories = useCategories().data ?? [];

    const createEventMutation = useMutation({
        mutationFn: (payload: EventPayload) => createEvent(payload, token!),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['events'] });
            queryClient.invalidateQueries({ queryKey: ['my-events'] });
            setStep('done');
        },
        onError: (err: Error) => setError(err.message || 'Submission failed.'),
    });
    const isLoading = createEventMutation.isPending;

    const [formData, setFormData] = useState({
        town: '',
        category: '',
        name: '',
        place: '',
        description: '',
        date: '',
        time: '',
        price: '',
        tags: [] as TagId[],
        link: '',
    });

    const { mutate: submitEvent } = createEventMutation;

    // Fire any pending submission stashed before the /auth redirect, once the user
    // returns authenticated.
    useEffect(() => {
        if (isInitializing || !isAuthenticated || !token) return;
        const raw = sessionStorage.getItem(PENDING_EVENT_KEY);
        if (!raw) return;
        sessionStorage.removeItem(PENDING_EVENT_KEY);

        let payload: EventPayload;
        try { payload = JSON.parse(raw) as EventPayload; } catch { return; }

        submitEvent(payload);
    }, [isAuthenticated, isInitializing, token, submitEvent]);

    const buildPayload = (): EventPayload => ({
        title: formData.name,
        town: formData.town,
        venue: formData.place,
        date: new Date(`${formData.date}T${formData.time}`).toISOString(),
        description: formData.description,
        price: parseFloat(formData.price) || 0,
        tags: formData.tags,
        link: formData.link,
        category: formData.category,
    });

    const handleTagToggle = (tagId: TagId) => {
        setFormData(prev => ({
            ...prev,
            tags: prev.tags.includes(tagId)
                ? prev.tags.filter(t => t !== tagId)
                : [...prev.tags, tagId],
        }));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const payload = buildPayload();

        if (!isAuthenticated) {
            try { sessionStorage.setItem(PENDING_EVENT_KEY, JSON.stringify(payload)); } catch { /* ignore */ }
            const params = new URLSearchParams({
                redirect: '/post',
                intent: 'post-event',
                heading: 'Almost there…',
                subheading: 'We just need an account so we can credit your post and let you manage it later.',
            });
            router.push(`/auth/signup?${params.toString()}`);
            return;
        }

        submitEvent(payload);
    };

    const townName = towns.find(t => t.slug === formData.town)?.name ?? formData.town;
    const categoryName =
        categories.find(c => c.slug === formData.category)?.display_name ?? formData.category;

    return (
        <main id="main-content" className="max-w-[560px] mx-auto px-4 py-12">
            <Link
                href="/"
                className="inline-block mb-6 text-[11px] uppercase tracking-widest no-underline text-[var(--color-text-muted)] hover:text-[var(--color-accent)] transition-colors"
            >
                ← Back to home
            </Link>
            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-1"
                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                >
                    Post an Event
                </h1>
                <p className="text-sm italic text-[var(--color-text-muted)]">
                    {step === 'done'
                        ? 'Thanks for contributing to the bulletin.'
                        : 'A couple of quick questions, then the details.'}
                </p>
            </header>

            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            {/* ── Step: where (1 of 2) ────────────────────────────────── */}
            {step === 'town' && (
                <section className="space-y-6">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1">
                        First, where is it?
                    </h2>

                    <Select
                        label="Town"
                        value={formData.town}
                        onChange={e => setFormData({ ...formData, town: e.target.value })}
                    >
                        <option value="">Select a town</option>
                        {towns.map(town => (
                            <option key={town.slug} value={town.slug}>{town.name}</option>
                        ))}
                    </Select>

                    <div className="flex justify-end pt-2">
                        <Button
                            type="button"
                            variant="primary"
                            disabled={!formData.town}
                            onClick={() => setStep('category')}
                        >
                            Continue
                        </Button>
                    </div>
                </section>
            )}

            {/* ── Step: what kind (2 of 2) ────────────────────────────── */}
            {step === 'category' && (
                <section className="space-y-6">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1">
                        And what kind of event?
                    </h2>

                    <Select
                        label="Event type"
                        value={formData.category}
                        onChange={e => setFormData({ ...formData, category: e.target.value })}
                    >
                        <option value="">Select a type</option>
                        {categories.map(cat => (
                            <option key={cat.slug} value={cat.slug}>{cat.display_name}</option>
                        ))}
                    </Select>

                    <div className="flex justify-between pt-2">
                        <Button type="button" variant="secondary" onClick={() => setStep('town')}>
                            Back
                        </Button>
                        <Button
                            type="button"
                            variant="primary"
                            disabled={!formData.category}
                            onClick={() => setStep('details')}
                        >
                            Continue
                        </Button>
                    </div>
                </section>
            )}

            {/* ── Step: details form ──────────────────────────────────── */}
            {step === 'details' && (
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="flex items-baseline justify-between border-b border-[var(--color-border-light)] pb-2">
                        <p className="text-xs uppercase tracking-wider">
                            <span className="font-black">{categoryName}</span>
                            <span className="text-[var(--color-text-muted)]"> in {townName}</span>
                        </p>
                        <button
                            type="button"
                            onClick={() => setStep('town')}
                            className="text-xs underline bg-transparent border-none cursor-pointer p-0 hover:text-[var(--color-accent)]"
                        >
                            ← change
                        </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Input
                            label="Event Name"
                            type="text"
                            required
                            value={formData.name}
                            onChange={e => setFormData({ ...formData, name: e.target.value })}
                        />
                        <Input
                            label="Venue/Place"
                            type="text"
                            required
                            value={formData.place}
                            onChange={e => setFormData({ ...formData, place: e.target.value })}
                        />
                    </div>

                    <Textarea
                        label="Description"
                        required
                        rows={3}
                        value={formData.description}
                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                    />

                    <Input
                        label="Link (optional)"
                        type="url"
                        placeholder="https://..."
                        value={formData.link}
                        onChange={e => setFormData({ ...formData, link: e.target.value })}
                    />

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Input
                            label="Date"
                            type="date"
                            required
                            value={formData.date}
                            onChange={e => setFormData({ ...formData, date: e.target.value })}
                        />
                        <Input
                            label="Time"
                            type="time"
                            required
                            value={formData.time}
                            onChange={e => setFormData({ ...formData, time: e.target.value })}
                        />
                        <Input
                            label="Price"
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder="0.00"
                            required
                            value={formData.price}
                            onChange={e => setFormData({ ...formData, price: e.target.value })}
                        />
                    </div>

                    <div>
                        <label className="block text-xs uppercase tracking-wider font-bold mb-2">Tags</label>
                        <div className="flex flex-wrap gap-1.5">
                            {FILTER_TAGS.map(tag => {
                                const isSelected = formData.tags.includes(tag.id);
                                return (
                                    <button
                                        key={tag.id}
                                        type="button"
                                        onClick={() => handleTagToggle(tag.id)}
                                        aria-pressed={isSelected}
                                        className={`px-2 py-1 text-[10px] uppercase tracking-wider border cursor-pointer transition-colors ${
                                            isSelected
                                                ? 'bg-[var(--color-text)] text-[var(--color-bg)] border-[var(--color-text)]'
                                                : 'bg-transparent border-[var(--color-border-light)] hover:bg-[var(--color-bg-alt)]'
                                        }`}
                                    >
                                        {tag.label}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div className="pt-4 border-t border-[var(--color-border-light)] flex justify-between gap-3">
                        <Button type="button" variant="secondary" onClick={() => setStep('category')}>
                            Back
                        </Button>
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Posting...' : 'Submit Post'}
                        </Button>
                    </div>
                </form>
            )}

            {/* ── Step: confirmation ──────────────────────────────────── */}
            {step === 'done' && (
                <section className="space-y-4">
                    <p className="text-base leading-relaxed">
                        Your posting has been submitted and is now <strong>under review</strong>.
                        Once an editor approves it, it&apos;ll appear on the board.
                    </p>
                    <div className="flex gap-3 pt-2">
                        <Link href="/" className="no-underline">
                            <Button variant="primary">Back to the board</Button>
                        </Link>
                    </div>
                </section>
            )}
        </main>
    );
}
