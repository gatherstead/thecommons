'use client';

import { useQuery } from '@tanstack/react-query';
import { getFacets } from '../services/eventService';
import type { EventWindow } from './useEvents';

export function useFacets(currentWindow: EventWindow) {
    return useQuery({
        queryKey: ['facets', currentWindow],
        queryFn: () => getFacets({ window: currentWindow }),
        retry: false,
    });
}
