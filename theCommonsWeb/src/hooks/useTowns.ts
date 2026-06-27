'use client';

import { useQuery } from '@tanstack/react-query';
import { getTowns } from '../services/eventService';

export function useTowns() {
    // Towns are near-static (admin/pipeline only) and cached 1hr on Django's
    // side; never re-fetch them within a session.
    return useQuery({ queryKey: ['towns'], queryFn: getTowns, staleTime: Infinity });
}
