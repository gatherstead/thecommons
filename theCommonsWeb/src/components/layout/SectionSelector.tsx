'use client';

import { useEffect, useRef, useState } from 'react';
import type { CategoryOption } from '../../models/eventsModels';

interface SectionSelectorProps {
    categories: CategoryOption[];
    selectedCategory: string | null;
    onCategorySelect: (slug: string | null) => void;
}

export function SectionSelector({ categories, selectedCategory, onCategorySelect }: SectionSelectorProps) {
    const [open, setOpen] = useState(false);
    const [locked, setLocked] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setOpen(false);
                setLocked(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    if (categories.length === 0) return null;

    const selected = categories.find(c => c.slug === selectedCategory);
    const label = selected ? selected.display_name : 'All Categories';

    const choose = (slug: string | null) => {
        onCategorySelect(slug);
        setOpen(false);
        setLocked(false);
    };

    const itemClass = (active: boolean) =>
        `w-full text-left px-3 py-1.5 text-xs uppercase tracking-wide cursor-pointer bg-transparent border-none transition-colors hover:bg-[var(--color-bg-alt)] ${
            active ? 'font-medium text-[var(--color-accent)]/60' : 'text-[var(--color-ink)]'
        }`;

    return (
        <div
            ref={ref}
            className="relative shrink-0"
            onMouseEnter={() => { setOpen(true); setLocked(false); }}
            onMouseLeave={() => { if (!locked) setOpen(false); }}
        >
            <button
                onClick={() => { setOpen(true); setLocked(true); }}
                aria-haspopup="listbox"
                aria-expanded={open}
                className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] font-black bg-transparent border-none cursor-pointer text-[var(--color-ink)] hover:text-[var(--color-accent)] transition-colors"
            >
                <span className="text-[var(--color-text-muted)]">Category:</span>
                <span>{label}</span>
                <span className={`transition-transform text-[8px] ${open ? 'rotate-180' : ''}`} aria-hidden="true">▼</span>
            </button>

            {open && (
                <ul
                    role="listbox"
                    className="absolute right-0 top-full z-30 min-w-[180px] bg-[var(--color-bg)] border-2 border-[var(--color-border)] py-1"
                >
                    <li>
                        <button
                            role="option"
                            aria-selected={selectedCategory === null}
                            onClick={() => choose(null)}
                            className={itemClass(selectedCategory === null)}
                        >
                            All Categories
                        </button>
                    </li>
                    {categories.map(cat => (
                        <li key={cat.slug}>
                            <button
                                role="option"
                                aria-selected={selectedCategory === cat.slug}
                                onClick={() => choose(cat.slug)}
                                className={itemClass(selectedCategory === cat.slug)}
                            >
                                {cat.display_name}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
