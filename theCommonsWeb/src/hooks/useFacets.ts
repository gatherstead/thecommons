'use client';

import { useQuery } from '@tanstack/react-query';
import { getFacets } from '../services/eventService';
import type { EventWindow } from './useEvents';

export function useFacets(currentWindow: EventWindow, selectedCategory: string | null) {
    return useQuery({
        queryKey: ['facets', currentWindow, selectedCategory],
        queryFn: () => getFacets({ window: currentWindow, category: selectedCategory ?? undefined }),
        retry: false,
    });
}
