import { useState } from 'react';
import type { TownOption } from '../../models/eventsModels';
import { FILTER_TAGS, type TagId } from '../../constants/tags';
import { createEvent } from '../../services/eventService';
import { Modal } from '../ui/Modal';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Textarea } from '../ui/Textarea';
import { Button } from '../ui/Button';

interface AddEventModalProps {
    isOpen: boolean;
    onClose: () => void;
    towns: TownOption[];
}

export function AddEventModal({ isOpen, onClose, towns }: AddEventModalProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [formData, setFormData] = useState({
        name: '',
        place: '',
        description: '',
        date: '',
        time: '',
        price: '',
        town: '',
        tags: [] as TagId[],
        link: '',
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);

        try {
            const isoDate = new Date(`${formData.date}T${formData.time}`).toISOString();

            await createEvent({
                title: formData.name,
                town: formData.town,
                venue: formData.place,
                date: isoDate,
                description: formData.description,
                price: parseFloat(formData.price) || 0.00,
                tags: formData.tags,
                link: formData.link,
            });

            alert('Event Created Successfully!');
            onClose();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    const handleTagToggle = (tagId: TagId) => {
        setFormData(prev => ({
            ...prev,
            tags: prev.tags.includes(tagId)
                ? prev.tags.filter(t => t !== tagId)
                : [...prev.tags, tagId]
        }));
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Post New Event">
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
                        required
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
                    <Button type="submit" variant="primary" disabled={isLoading}>
                        {isLoading ? 'Posting...' : 'Submit Post'}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
