'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
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

function isEventWindow(value: string | null): value is EventWindow {
    return value === '3months' || value === '6months' || value === '12months' || value === 'past';
}

// Builds the ?tag=&town=&category=&window=&page= query string for the current
// filter state, omitting anything at its default value so a filter-free view
// keeps a bare URL. Param names/repetition MUST match the API (see 48.12):
// tag repeats (AND), town repeats (OR).
function filtersToSearchParams(state: {
    selectedTags: string[];
    selectedTowns: string[];
    selectedCategory: string | null;
    currentWindow: EventWindow;
    currentPage: number;
}): URLSearchParams {
    const params = new URLSearchParams();
    for (const t of state.selectedTags) params.append('tag', t);
    for (const t of state.selectedTowns) params.append('town', t);
    if (state.selectedCategory) params.set('category', state.selectedCategory);
    if (state.currentWindow !== '3months') params.set('window', state.currentWindow);
    if (state.currentPage > 1) params.set('page', String(state.currentPage));
    return params;
}

async function fetchForWindow(w: EventWindow, category?: string, tags?: string[], towns?: string[]) {
    if (w === 'past') return getEvents({ window: 'past', category, tags, towns });
    if (w === '3months') return getEvents({ category, tags, towns });
    const before = new Date(Date.now() + (w === '6months' ? 180 : 365) * DAY_MS).toISOString();
    return getEvents({ before, category, tags, towns });
}

type ChangeKind = 'initial' | 'window' | 'category' | 'page' | 'facet';

export function useEvents(viewMode: ViewMode = 'feed') {
    const queryClient = useQueryClient();
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();

    // Read once at mount so a pasted/reloaded URL reproduces the same filtered
    // view. Later URL changes are driven BY this state (see the sync effect
    // below), not the other way around, so we intentionally don't re-read
    // searchParams after the first render.
    const [selectedCategory, setSelectedCategoryState] = useState<string | null>(
        () => searchParams.get('category'),
    );
    const [currentWindow, setCurrentWindow] = useState<EventWindow>(() => {
        const w = searchParams.get('window');
        return isEventWindow(w) ? w : '3months';
    });
    // null means the first page of the current window; otherwise a next/prev URL.
    const [currentPageUrl, setCurrentPageUrl] = useState<string | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    // A page > 1 in the URL can't be fetched directly (pagination is opaque
    // DRF next/prev links), so on mount we remember the target and walk
    // forward one page at a time once page 1 has loaded. Cleared once reached
    // (or once we run out of next pages). useRef's argument is re-evaluated
    // every render but only ever *used* on the first, so this cheap parse is fine.
    const initialTargetPage = (() => {
        const p = Number(searchParams.get('page'));
        return Number.isInteger(p) && p > 1 ? p : null;
    })();
    const targetPageRef = useRef<number | null>(initialTargetPage);
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

    // useToggleSet only consumes this initial array on its first render, so
    // recomputing it from searchParams every render is harmless.
    const { selected: selectedTags, toggle: toggleTagRaw, clear: clearTagsRaw } = useToggleSet<TagId>(
        searchParams.getAll('tag') as TagId[],
    );
    const { selected: selectedTowns, toggle: toggleTownRaw, clear: clearTownsRaw } = useToggleSet<TownId>(
        searchParams.getAll('town'),
    );

    const pageQuery = useQuery({
        queryKey: currentPageUrl
            ? ['events', 'page', currentPageUrl]
            : ['events', 'window', currentWindow, selectedCategory, selectedTags, selectedTowns],
        queryFn: () =>
            currentPageUrl
                ? getEvents({ pageUrl: currentPageUrl })
                : fetchForWindow(currentWindow, selectedCategory ?? undefined, selectedTags, selectedTowns),
        placeholderData: keepPreviousData,
    });

    // Tag/town selection is server-side filtering now (it changes `results` and
    // `count`), so — like category — it must reset pagination back to page 1 and
    // invalidate the calendar's month cache (month fetches also carry tag/town
    // params, see prefetchMonth below).
    const resetForFacetChange = () => {
        lastChangeRef.current = 'facet';
        setCurrentPageUrl(null);
        setCurrentPage(1);
        setMonthEvents([]);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
    };

    const toggleTag = (tag: TagId) => {
        resetForFacetChange();
        toggleTagRaw(tag);
    };

    const toggleTown = (town: TownId) => {
        resetForFacetChange();
        toggleTownRaw(town);
    };

    const clearTags = () => {
        resetForFacetChange();
        clearTagsRaw();
    };

    const clearTowns = () => {
        resetForFacetChange();
        clearTownsRaw();
    };

    // Switching between feed and calendar invalidates the calendar's month
    // cache and resets pagination (window and category are preserved — they're
    // shared filter state, not view-local).
    useEffect(() => {
        lastChangeRef.current = 'initial';
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
            queryKey: ['events', 'month', key, selectedTags, selectedTowns],
            queryFn: () => getEvents({ after, before, tags: selectedTags, towns: selectedTowns }),
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
            queryClient.getQueryData<EventsPage>(['events', 'month', key, selectedTags, selectedTowns]) !==
                undefined;
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
    // eslint-disable-next-line react-hooks/refs
    const isLoading =
        pageQuery.isPending ||
        (isPlaceholder && (lastChangeRef.current === 'category' || lastChangeRef.current === 'facet'));
    // eslint-disable-next-line react-hooks/refs
    const isLoadingWindow = isPlaceholder && lastChangeRef.current === 'window';
    // eslint-disable-next-line react-hooks/refs
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

    // Restores a page > 1 found in the URL on mount by walking forward one
    // page at a time once the current page has loaded (pagination cursors are
    // opaque DRF next/prev links, so we can't jump straight to page N). Stops
    // once the target is reached or we run out of `next` pages.
    useEffect(() => {
        if (targetPageRef.current === null || isLoadingPage) return;
        if (!pageQuery.data) return; // still loading the current page — nothing to act on yet
        if (currentPage < targetPageRef.current && pageQuery.data.next) {
            nextPage();
        } else {
            targetPageRef.current = null;
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [currentPage, pageQuery.data, isLoadingPage]);

    // Keeps the URL in sync with filter state so the view is shareable,
    // bookmarkable, and restored on reload. Uses replace (not push) so
    // filtering doesn't spam browser history with one entry per click.
    useEffect(() => {
        const params = filtersToSearchParams({
            selectedTags,
            selectedTowns,
            selectedCategory,
            currentWindow,
            currentPage,
        });
        const qs = params.toString();
        router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedTags, selectedTowns, selectedCategory, currentWindow, currentPage, pathname, router]);

    // Tag/town filtering now happens server-side (see `_filtered_events_queryset`
    // in backendServer/events/views.py) so both `pageQuery.data.results` and
    // `monthEvents` already reflect the current filter selection. This is just a
    // merge + chronological sort, not a filter.
    const filteredEvents = useMemo(() => {
        return mergeEvents(pageQuery.data?.results ?? [], monthEvents).sort(
            (a, b) => a.date.getTime() - b.date.getTime(),
        );
    }, [pageQuery.data, monthEvents]);

    const clearFilters = () => {
        clearTags();
        clearTowns();
        if (selectedCategory !== null) {
            setCategory(null);
        }
        setWindow('3months');
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
        clearTowns,
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
