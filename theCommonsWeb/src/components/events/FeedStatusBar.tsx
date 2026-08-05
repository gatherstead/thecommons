'use client';

import { TimeWindowSelector } from '../layout/TimeWindowSelector';
import type { EventWindow } from '../../hooks/useEvents';

interface FeedStatusBarProps {
    countLabel: string;
    currentWindow: EventWindow;
    onWindowChange: (w: EventWindow) => void;
}

export function FeedStatusBar({
    countLabel,
    currentWindow,
    onWindowChange,
}: FeedStatusBarProps) {
    return (
        <div className="flex items-center justify-between gap-3 py-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-[var(--color-text-muted)]">
                {countLabel}
            </p>
            <div className="flex items-center gap-4">
                <TimeWindowSelector currentWindow={currentWindow} onWindowChange={onWindowChange} />
            </div>
        </div>
    );
}
