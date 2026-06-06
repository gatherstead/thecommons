'use client';

import { useEffect, useRef, useState } from 'react';
import type { EventWindow } from '../../hooks/useEvents';

const WINDOW_OPTIONS: { id: EventWindow; label: string; short: string }[] = [
    { id: '3months', label: 'Next 3 Months', short: '3 Months' },
    { id: '6months', label: 'Next 6 Months', short: '6 Months' },
    { id: '12months', label: 'Next 12 Months', short: '12 Months' },
    { id: 'past', label: 'Past Events', short: 'Past' },
];

interface TimeWindowSelectorProps {
    currentWindow: EventWindow;
    onWindowChange: (w: EventWindow) => void;
}

export function TimeWindowSelector({ currentWindow, onWindowChange }: TimeWindowSelectorProps) {
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

    const selected = WINDOW_OPTIONS.find(o => o.id === currentWindow) ?? WINDOW_OPTIONS[0];

    const choose = (id: EventWindow) => {
        onWindowChange(id);
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
                <span className="text-[var(--color-text-muted)]">Range:</span>
                <span>{selected.short}</span>
                <span className={`transition-transform text-[8px] ${open ? 'rotate-180' : ''}`} aria-hidden="true">▼</span>
            </button>

            {open && (
                <ul
                    role="listbox"
                    className="absolute left-0 top-full z-30 min-w-[160px] bg-[var(--color-bg)] border-2 border-[var(--color-border)] py-1"
                >
                    {WINDOW_OPTIONS.map(opt => (
                        <li key={opt.id}>
                            <button
                                role="option"
                                aria-selected={currentWindow === opt.id}
                                onClick={() => choose(opt.id)}
                                className={itemClass(currentWindow === opt.id)}
                            >
                                {opt.label}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
