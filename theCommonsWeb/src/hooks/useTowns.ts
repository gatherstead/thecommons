'use client';

import { useQuery } from '@tanstack/react-query';
import { getTowns } from '../services/eventService';

export function useTowns() {
    return useQuery({ queryKey: ['towns'], queryFn: getTowns, staleTime: Infinity });
}
