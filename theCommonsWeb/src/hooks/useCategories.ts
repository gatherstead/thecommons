'use client';

import { useQuery } from '@tanstack/react-query';
import { getCategories } from '../services/eventService';

export function useCategories() {
    // Categories are near-static; never re-fetch within a session.
    return useQuery({ queryKey: ['categories'], queryFn: getCategories, staleTime: Infinity });
}
