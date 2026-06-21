'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TownOption } from '../../models/eventsModels';
import { FILTER_TAGS, type TagId } from '../../constants/tags';
import { getStagedEvent, updateStagedEvent } from '../../services/eventService';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Textarea } from '../ui/Textarea';
import { Button } from '../ui/Button';

interface EditEventModalProps {
    isOpen: boolean;
    onClose: () => void;
    eventId: string;
    token: string;
    towns: TownOption[];
}

type StagedEventDetail = Awaited<ReturnType<typeof getStagedEvent>>;

export function EditEventModal({ isOpen, onClose, eventId, token, towns }: EditEventModalProps) {
    const stagedQuery = useQuery({
        queryKey: ['staged-event', eventId, token],
        queryFn: () => getStagedEvent(token, eventId),
        enabled: isOpen && !!eventId,
    });

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Edit Event">
            {stagedQuery.isError && (
                <div className="mb-4 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold" role="alert">
                    Could not load event details.
                </div>
            )}
            {stagedQuery.isLoading ? (
                <div className="space-y-3 py-4">
                    {[1, 2, 3].map(i => <div key={i} className="skeleton-block h-10 w-full" />)}
                </div>
            ) : stagedQuery.data ? (
                <EditEventForm
                    key={eventId}
                    initial={stagedQuery.data}
                    eventId={eventId}
                    token={token}
                    towns={towns}
                    onClose={onClose}
                />
            ) : null}
        </Modal>
    );
}

interface EditEventFormProps {
    initial: StagedEventDetail;
    eventId: string;
    token: string;
    towns: TownOption[];
    onClose: () => void;
}

function EditEventForm({ initial, eventId, token, towns, onClose }: EditEventFormProps) {
    const queryClient = useQueryClient();
    const [error, setError] = useState<string | null>(null);
    // Draft state seeded once from the fetched event; deliberately not synced
    // to later refetches so an invalidation can't clobber in-progress edits.
    const [formData, setFormData] = useState(() => {
        const dt = initial.date ? new Date(initial.date) : null;
        return {
            name: initial.title,
            place: initial.venue,
            town: initial.town,
            description: initial.description,
            date: dt ? dt.toISOString().split('T')[0] : '',
            time: dt ? dt.toTimeString().slice(0, 5) : '',
            price: initial.price || '',
            tags: (initial.tags || []) as TagId[],
            link: initial.link || '',
        };
    });

    const updateMutation = useMutation({
        mutationFn: () =>
            updateStagedEvent(token, eventId, {
                title: formData.name,
                venue: formData.place,
                town: formData.town,
                date: new Date(`${formData.date}T${formData.time}`).toISOString(),
                description: formData.description,
                price: formData.price || null,
                tags: formData.tags,
                link: formData.link,
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['my-events'] });
            queryClient.invalidateQueries({ queryKey: ['staged-event', eventId] });
            onClose();
        },
        onError: () => setError('Failed to save changes. Please try again.'),
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        updateMutation.mutate();
    };

    const handleTagToggle = (tagId: TagId) => {
        setFormData(prev => ({
            ...prev,
            tags: prev.tags.includes(tagId)
                ? prev.tags.filter(t => t !== tagId)
                : [...prev.tags, tagId],
        }));
    };

    return (
        <>
            {error && (
                <div className="mb-4 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold" role="alert">
                    {error}
                </div>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
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
                        value={formData.price}
                        onChange={e => setFormData({ ...formData, price: e.target.value })}
                    />
                </div>

                <Select
                    label="Town"
                    required
                    value={formData.town}
                    onChange={e => setFormData({ ...formData, town: e.target.value })}
                >
                    <option value="">Select a town</option>
                    {towns.map(town => (
                        <option key={town.slug} value={town.slug}>{town.name}</option>
                    ))}
                </Select>

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

                <div className="pt-4 border-t border-[var(--color-border-light)] flex justify-end gap-3">
                    <Button type="button" variant="secondary" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button type="submit" variant="primary" disabled={updateMutation.isPending}>
                        {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
                    </Button>
                </div>
            </form>
        </>
    );
}
