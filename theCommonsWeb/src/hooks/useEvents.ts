'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { getEvents, getTowns } from '../services/eventService';
import { type FrontendEvent, type TownOption } from '../models/eventsModels';
import { type TagId } from '../constants/tags';
import { useToggleSet } from './useToggleSet';

export type TownId = string;
export type ViewMode = 'feed' | 'calendar';

function adjMonth(year: number, month: number, delta: number): { year: number; month: number } {
    const d = new Date(year, month - 1 + delta, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function mergeEvents(existing: FrontendEvent[], incoming: FrontendEvent[]): FrontendEvent[] {
    const ids = new Set(existing.map(e => e.id));
    return [...existing, ...incoming.filter(e => !ids.has(e.id))];
}

export function useEvents(viewMode: ViewMode = 'feed') {
    const [events, setEvents] = useState<FrontendEvent[]>([]);
    const [towns, setTowns] = useState<TownOption[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [showingPastEvents, setShowingPastEvents] = useState(false);
    const [isLoadingPast, setIsLoadingPast] = useState(false);
    const [prefetchedPastEvents, setPrefetchedPastEvents] = useState<FrontendEvent[] | null>(null);
    const [isLoadingMonth, setIsLoadingMonth] = useState(false);
    const fetchedMonths = useRef<Set<string>>(new Set());
    // Maps empty month keys to the number of 150 ms revisit flashes already shown (max 3).
    const emptyMonthVisits = useRef<Map<string, number>>(new Map());

    const { selected: selectedTags, toggle: toggleTag, clear: clearTags } = useToggleSet<TagId>([]);
    const { selected: selectedTowns, toggle: toggleTown, clear: clearTowns } = useToggleSet<TownId>([]);

    const fetchEvents = async () => {
        setIsLoading(true);
        setPrefetchedPastEvents(null);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
        const before = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
        const [data, townData] = await Promise.all([
            getEvents({ before: before.toISOString() }),
            getTowns(),
        ]);
        setEvents(data);
        setTowns(townData);
        setIsLoading(false);
        // Background prefetch past events after initial paint — no await intentional
        getEvents({ include_past: true }).then(setPrefetchedPastEvents);
    };

    // Background-fetches a single month and merges into state. No-op if already fetched.
    // Records months that came back empty so fetchMonth can flash the skeleton on revisits.
    const prefetchMonth = async (year: number, month: number) => {
        const key = `${year}-${String(month).padStart(2, '0')}`;
        if (fetchedMonths.current.has(key)) return;
        fetchedMonths.current.add(key);
        const after = new Date(year, month - 1, 1).toISOString();
        const before = new Date(year, month, 0, 23, 59, 59).toISOString();
        const data = await getEvents({ after, before });
        if (data.length === 0) emptyMonthVisits.current.set(key, 0);
        setEvents(prev => mergeEvents(prev, data));
    };

    // Foreground-fetches a month then cascade-prefetches adjacent months.
    // - Uncached month: skeleton for at least 350 ms (fetch + timer in parallel).
    // - Cached but empty month: flash skeleton for 150 ms so users know we tried.
    // - Cached with events: no skeleton, instant.
    const fetchMonth = async (year: number, month: number) => {
        const key = `${year}-${String(month).padStart(2, '0')}`;
        const alreadyFetched = fetchedMonths.current.has(key);
        const revisits = emptyMonthVisits.current.get(key);

        if (!alreadyFetched) {
            setIsLoadingMonth(true);
            await Promise.all([
                prefetchMonth(year, month),
                new Promise<void>(r => setTimeout(r, 350)),
            ]);
            setIsLoadingMonth(false);
        } else if (revisits !== undefined && revisits < 3) {
            emptyMonthVisits.current.set(key, revisits + 1);
            setIsLoadingMonth(true);
            await new Promise<void>(r => setTimeout(r, 150));
            setIsLoadingMonth(false);
        }

        const prev = adjMonth(year, month, -1);
        const next = adjMonth(year, month, +1);
        prefetchMonth(prev.year, prev.month);
        prefetchMonth(next.year, next.month);
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        setShowingPastEvents(false);
        fetchEvents();
    }, [viewMode]);

    const loadPastEvents = async () => {
        if (prefetchedPastEvents) {
            setEvents(prefetchedPastEvents);
            setShowingPastEvents(true);
            return;
        }
        setIsLoadingPast(true);
        const data = await getEvents({ include_past: true });
        setEvents(data);
        setShowingPastEvents(true);
        setIsLoadingPast(false);
    };

    const filteredEvents = useMemo(() => {
        return events
            .filter(event => {
                if (selectedTowns.length > 0 && !selectedTowns.includes(event.town as TownId)) {
                    return false;
                }
                if (selectedTags.length > 0 && !selectedTags.every(tag => event.tags.includes(tag))) {
                    return false;
                }
                return true;
            })
            .sort((a, b) => a.date.getTime() - b.date.getTime());
    }, [selectedTags, selectedTowns, events]);

    const clearFilters = () => {
        clearTags();
        clearTowns();
    };

    return {
        filteredEvents,
        towns,
        isLoading,
        showingPastEvents,
        isLoadingPast,
        loadPastEvents,
        fetchMonth,
        prefetchMonth,
        isLoadingMonth,
        selectedTags,
        selectedTowns,
        toggleTag,
        toggleTown,
        clearFilters,
        refetch: () => {
            if (showingPastEvents) {
                setIsLoading(true);
                getEvents({ include_past: true }).then(data => {
                    setEvents(data);
                    setIsLoading(false);
                });
            } else {
                fetchEvents();
            }
        },
    };
}
