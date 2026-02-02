import { useState } from 'react';
import { TOWNS, type TownId } from './TownMultiselect';
import { FILTER_TAGS, type TagId } from './TagFilter';
import { createEvent } from '../services/eventService';

interface AddEventModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export function AddEventModal({ isOpen, onClose }: AddEventModalProps) {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [formData, setFormData] = useState({
        name: '',
        place: '',
        description: '',
        date: '',
        time: '',
        price: '', // We keep this as string in state for easier input handling
        town: '' as TownId,
        tags: [] as TagId[],
    });

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);

        try {
            // 2. Prepare data for the backend
            // Note: We need to ensure 'time' is in a format Date() accepts (like HH:MM)
            // If you use a text input for time, this might be flaky. 
            // Consider type="time" for the input below.
            const isoDate = new Date(`${formData.date}T${formData.time}`).toISOString();

            await createEvent({
                title: formData.name,
                town: formData.town,
                venue: formData.place,
                date: isoDate,
                description: formData.description,
                price: parseFloat(formData.price) || 0.00,
                tags: formData.tags, // Sending the array of IDs ['family', 'outdoor']
            });

            // Success!
            alert('Event Created Successfully!');
            onClose();
            // Optional: Reset form here
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <div className="bg-[var(--color-paper)] border-4 border-[var(--color-border)] w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 md:p-8 shadow-2xl">
                <div className="flex justify-between items-center mb-6 border-b-2 border-[var(--color-border)] pb-2">
                    <h2 className="font-[var(--font-headline)] text-3xl font-bold uppercase tracking-tight">Post New Event</h2>
                    <button onClick={onClose} className="text-3xl hover:text-[var(--color-accent)] cursor-pointer">&times;</button>
                </div>

                {/* Show Error Messages if API fails */}
                {error && (
                    <div className="mb-4 p-3 bg-red-100 border-2 border-red-500 text-red-700 font-bold">
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-6">
                    {/* ... (Event Name and Venue inputs remain the same) ... */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Event Name</label>
                            <input
                                type="text"
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.name}
                                onChange={e => setFormData({ ...formData, name: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Venue/Place</label>
                            <input
                                type="text"
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.place}
                                onChange={e => setFormData({ ...formData, place: e.target.value })}
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Description</label>
                        <textarea
                            required
                            rows={3}
                            className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none resize-none"
                            value={formData.description}
                            onChange={e => setFormData({ ...formData, description: e.target.value })}
                        />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Date</label>
                            <input
                                type="date"
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.date}
                                onChange={e => setFormData({ ...formData, date: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Time</label>
                            {/* CHANGED: type="time" ensures the format is HH:MM for easy parsing */}
                            <input
                                type="time"
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.time}
                                onChange={e => setFormData({ ...formData, time: e.target.value })}
                            />
                        </div>
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Price</label>
                            {/* CHANGED: type="number" ensures we send a valid decimal */}
                            <input
                                type="number"
                                step="0.01"
                                placeholder="0.00"
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.price}
                                onChange={e => setFormData({ ...formData, price: e.target.value })}
                            />
                        </div>
                    </div>

                    {/* ... (Rest of the form remains exactly the same) ... */}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-1">Town</label>
                            <select
                                required
                                className="w-full bg-transparent border-2 border-[var(--color-border)] p-2 font-[var(--font-body)] focus:border-[var(--color-accent)] outline-none"
                                value={formData.town}
                                onChange={e => setFormData({ ...formData, town: e.target.value as TownId })}
                            >
                                <option value="">Select a town</option>
                                {TOWNS.map(town => (
                                    <option key={town.id} value={town.id}>{town.name}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block font-[var(--font-headline)] uppercase tracking-wider text-sm font-bold mb-2">Tags</label>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_TAGS.map(tag => {
                                const isSelected = formData.tags.includes(tag.id);
                                return (
                                    <button
                                        key={tag.id}
                                        type="button"
                                        onClick={() => handleTagToggle(tag.id)}
                                        className={`px-3 py-1 text-xs border-2 transition-all cursor-pointer ${isSelected
                                            ? 'bg-[var(--color-ink)] text-[var(--color-paper)] border-[var(--color-ink)]'
                                            : 'bg-transparent text-[var(--color-ink)] border-[var(--color-border)] hover:bg-[#ebe7de]'
                                            }`}
                                    >
                                        {tag.label}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div className="pt-6 border-t-2 border-[var(--color-border)] flex justify-end gap-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-6 py-2 border-2 border-[var(--color-border)] font-[var(--font-headline)] font-bold uppercase tracking-wider hover:bg-[#ebe7de] cursor-pointer"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading}
                            className="px-8 py-2 bg-[var(--color-ink)] text-[var(--color-paper)] border-2 border-[var(--color-ink)] font-[var(--font-headline)] font-bold uppercase tracking-wider hover:bg-[var(--color-accent)] hover:border-[var(--color-accent)] transition-colors cursor-pointer disabled:opacity-50"
                        >
                            {isLoading ? 'Posting...' : 'Submit Post'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}