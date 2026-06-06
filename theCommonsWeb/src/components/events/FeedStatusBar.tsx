'use client';

import { TimeWindowSelector } from '../layout/TimeWindowSelector';
import { SectionSelector } from '../layout/SectionSelector';
import type { EventWindow } from '../../hooks/useEvents';
import type { CategoryOption } from '../../models/eventsModels';

interface FeedStatusBarProps {
    countLabel: string;
    currentWindow: EventWindow;
    onWindowChange: (w: EventWindow) => void;
    categories: CategoryOption[];
    selectedCategory: string | null;
    onCategorySelect: (slug: string | null) => void;
}

export function FeedStatusBar({
    countLabel,
    currentWindow,
    onWindowChange,
    categories,
    selectedCategory,
    onCategorySelect,
}: FeedStatusBarProps) {
    return (
        <div className="flex items-center justify-between gap-3 py-2">
            <p className="text-[10px] uppercase tracking-[0.2em] font-black text-[var(--color-text-muted)]">
                {countLabel}
            </p>
            <div className="flex items-center gap-4">
                <TimeWindowSelector currentWindow={currentWindow} onWindowChange={onWindowChange} />
                <SectionSelector
                    categories={categories}
                    selectedCategory={selectedCategory}
                    onCategorySelect={onCategorySelect}
                />
            </div>
        </div>
    );
}
