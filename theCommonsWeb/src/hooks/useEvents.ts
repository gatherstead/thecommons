'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { getEvents, type EventsPage } from '../services/eventService';
import { type FrontendEvent } from '../models/eventsModels';
import { type TagId } from '../constants/tags';
import { useToggleSet } from './useToggleSet';
import { useTowns } from './useTowns';
import { useCategories } from './useCategories';

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

function monthKey(year: number, month: number): string {
    return `${year}-${String(month).padStart(2, '0')}`;
}

export type EventWindow = '3months' | '6months' | '12months' | 'past';

const DAY_MS = 24 * 60 * 60 * 1000;

async function fetchForWindow(w: EventWindow, category?: string) {
    if (w === 'past') return getEvents({ window: 'past', category });
    if (w === '3months') return getEvents({ category });
    const before = new Date(Date.now() + (w === '6months' ? 180 : 365) * DAY_MS).toISOString();
    return getEvents({ before, category });
}

type ChangeKind = 'initial' | 'window' | 'category' | 'page';

export function useEvents(viewMode: ViewMode = 'feed') {
    const queryClient = useQueryClient();

    const [selectedCategory, setSelectedCategoryState] = useState<string | null>(null);
    const [currentWindow, setCurrentWindow] = useState<EventWindow>('3months');
    // null means the first page of the current window; otherwise a next/prev URL.
    const [currentPageUrl, setCurrentPageUrl] = useState<string | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    // Month results fetched for the calendar view, merged client-side into the
    // rendered list. This is UI accumulation state, not cache state — the cache
    // lives in TanStack Query under ['events', 'month', key].
    const [monthEvents, setMonthEvents] = useState<FrontendEvent[]>([]);
    const [isLoadingMonth, setIsLoadingMonth] = useState(false);
    // Months already merged into monthEvents this mount (request dedup is
    // handled by TanStack Query; this only prevents redundant re-merges).
    const fetchedMonths = useRef<Set<string>>(new Set());
    // Maps empty month keys to the number of 150 ms revisit flashes already shown (max 3).
    const emptyMonthVisits = useRef<Map<string, number>>(new Map());
    // Which UI action caused the current query-key change — drives which
    // loading indicator shows while placeholder data is displayed.
    const lastChangeRef = useRef<ChangeKind>('initial');

    const townsQuery = useTowns();
    const categoriesQuery = useCategories();

    const pageQuery = useQuery({
        queryKey: currentPageUrl
            ? ['events', 'page', currentPageUrl]
            : ['events', 'window', currentWindow, selectedCategory],
        queryFn: () =>
            currentPageUrl
                ? getEvents({ pageUrl: currentPageUrl })
                : fetchForWindow(currentWindow, selectedCategory ?? undefined),
        placeholderData: keepPreviousData,
    });

    const { selected: selectedTags, toggle: toggleTag, clear: clearTags } = useToggleSet<TagId>([]);
    const { selected: selectedTowns, toggle: toggleTown, clear: clearTowns } = useToggleSet<TownId>([]);

    // Switching between feed and calendar resets to the 3-month window
    // (category is preserved, matching the previous behavior).
    useEffect(() => {
        lastChangeRef.current = 'initial';
        setCurrentWindow('3months');
        setCurrentPageUrl(null);
        setCurrentPage(1);
        setMonthEvents([]);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
    }, [viewMode]);

    // Background-fetches a single month and merges into state. No-op if already
    // merged this mount; TanStack Query dedupes concurrent fetches and serves
    // warm cache instantly. Records months that came back empty so fetchMonth
    // can flash the skeleton on revisits.
    const prefetchMonth = async (year: number, month: number) => {
        const key = monthKey(year, month);
        if (fetchedMonths.current.has(key)) return;
        fetchedMonths.current.add(key);
        const after = new Date(year, month - 1, 1).toISOString();
        const before = new Date(year, month, 0, 23, 59, 59).toISOString();
        const page = await queryClient.fetchQuery({
            queryKey: ['events', 'month', key],
            queryFn: () => getEvents({ after, before }),
        });
        if (page.results.length === 0 && !emptyMonthVisits.current.has(key)) {
            emptyMonthVisits.current.set(key, 0);
        }
        setMonthEvents(prev => mergeEvents(prev, page.results));
    };

    // Foreground-fetches a month then cascade-prefetches adjacent months.
    // - Uncached month: skeleton for at least 350 ms (fetch + timer in parallel).
    // - Cached but empty month: flash skeleton for 150 ms so users know we tried.
    // - Cached with events: no skeleton, instant.
    const fetchMonth = async (year: number, month: number) => {
        const key = monthKey(year, month);
        const alreadyFetched =
            fetchedMonths.current.has(key) ||
            queryClient.getQueryData<EventsPage>(['events', 'month', key]) !== undefined;
        const revisits = emptyMonthVisits.current.get(key);

        if (!alreadyFetched) {
            setIsLoadingMonth(true);
            await Promise.all([
                prefetchMonth(year, month),
                new Promise<void>(r => setTimeout(r, 350)),
            ]);
            setIsLoadingMonth(false);
        } else {
            // Warm cache from a previous mount still needs merging into this mount's state.
            prefetchMonth(year, month);
            if (revisits !== undefined && revisits < 3) {
                emptyMonthVisits.current.set(key, revisits + 1);
                setIsLoadingMonth(true);
                await new Promise<void>(r => setTimeout(r, 150));
                setIsLoadingMonth(false);
            }
        }

        const prev = adjMonth(year, month, -1);
        const next = adjMonth(year, month, +1);
        prefetchMonth(prev.year, prev.month);
        prefetchMonth(next.year, next.month);
    };

    const isPlaceholder = pageQuery.isPlaceholderData;
    const isLoading = pageQuery.isPending || (isPlaceholder && lastChangeRef.current === 'category');
    const isLoadingWindow = isPlaceholder && lastChangeRef.current === 'window';
    const isLoadingPage = isPlaceholder && lastChangeRef.current === 'page';

    const setWindow = (w: EventWindow) => {
        lastChangeRef.current = 'window';
        setCurrentPageUrl(null);
        setCurrentPage(1);
        setCurrentWindow(w);
    };

    const setCategory = (slug: string | null) => {
        lastChangeRef.current = 'category';
        setSelectedCategoryState(slug);
        setCurrentWindow('3months');
        setCurrentPageUrl(null);
        setCurrentPage(1);
        setMonthEvents([]);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
    };

    const nextPage = () => {
        if (!pageQuery.data?.next || isLoadingPage) return;
        lastChangeRef.current = 'page';
        setCurrentPageUrl(pageQuery.data.next);
        setCurrentPage(p => p + 1);
    };

    const prevPage = () => {
        if (!pageQuery.data?.previous || isLoadingPage) return;
        lastChangeRef.current = 'page';
        // Page 1 is keyed by window+category, so going back to it reuses that cache entry.
        setCurrentPageUrl(currentPage === 2 ? null : pageQuery.data.previous);
        setCurrentPage(p => p - 1);
    };

    const events = useMemo(
        () => mergeEvents(pageQuery.data?.results ?? [], monthEvents),
        [pageQuery.data, monthEvents],
    );

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
        if (selectedCategory !== null) {
            setCategory(null);
        }
    };

    const totalCount = pageQuery.data?.count ?? 0;
    const PAGE_SIZE = 30;
    const totalPages = Math.ceil(totalCount / PAGE_SIZE) || 1;

    return {
        filteredEvents,
        towns: townsQuery.data ?? [],
        categories: categoriesQuery.data ?? [],
        isLoading,
        currentWindow,
        isLoadingWindow,
        setWindow,
        nextPage,
        prevPage,
        isLoadingPage,
        currentPage,
        totalPages,
        totalCount,
        fetchMonth,
        prefetchMonth,
        isLoadingMonth,
        selectedTags,
        selectedTowns,
        selectedCategory,
        toggleTag,
        toggleTown,
        setCategory,
        clearFilters,
        refetch: () => {
            lastChangeRef.current = 'initial';
            fetchedMonths.current.clear();
            emptyMonthVisits.current.clear();
            setMonthEvents([]);
            setCurrentPageUrl(null);
            setCurrentPage(1);
            queryClient.invalidateQueries({ queryKey: ['events'] });
        },
    };
}
