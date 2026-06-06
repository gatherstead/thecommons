'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { getEvents, getTowns, getCategories, type EventsPage } from '../services/eventService';
import { type FrontendEvent, type TownOption, type CategoryOption } from '../models/eventsModels';
import { type TagId } from '../constants/tags';
import { useToggleSet } from './useToggleSet';
import {
    eventCacheKey,
    getCachedPage,
    setCachedPage,
    getCachedTowns,
    setCachedTowns,
    getCachedCategories,
    setCachedCategories,
    clearEventCache,
} from '../services/eventCache';

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

export type EventWindow = '3months' | '6months' | '12months' | 'past';

const DAY_MS = 24 * 60 * 60 * 1000;

async function fetchForWindow(w: EventWindow, category?: string) {
    if (w === 'past') return getEvents({ window: 'past', category });
    if (w === '3months') return getEvents({ category });
    const before = new Date(Date.now() + (w === '6months' ? 180 : 365) * DAY_MS).toISOString();
    return getEvents({ before, category });
}

export function useEvents(viewMode: ViewMode = 'feed') {
    // On (re)mount the view always starts at the 3-month window with no category,
    // so seed initial state from the module cache to skip the loading flash when
    // returning to a view we already fetched this session.
    const initialPage = getCachedPage(eventCacheKey('3months', null));

    const [events, setEvents] = useState<FrontendEvent[]>(initialPage?.results ?? []);
    const [towns, setTowns] = useState<TownOption[]>(() => getCachedTowns() ?? []);
    const [categories, setCategories] = useState<CategoryOption[]>(() => getCachedCategories() ?? []);
    const [selectedCategory, setSelectedCategoryState] = useState<string | null>(null);
    const selectedCategoryRef = useRef<string | null>(null);
    const [isLoading, setIsLoading] = useState(!initialPage);
    const [currentWindow, setCurrentWindow] = useState<EventWindow>('3months');
    const [isLoadingWindow, setIsLoadingWindow] = useState(false);
    const [isLoadingPage, setIsLoadingPage] = useState(false);
    const [nextPageUrl, setNextPageUrl] = useState<string | null>(initialPage?.next ?? null);
    const [prevPageUrl, setPrevPageUrl] = useState<string | null>(initialPage?.previous ?? null);
    const [totalCount, setTotalCount] = useState(initialPage?.count ?? 0);
    const [currentPage, setCurrentPage] = useState(1);
    const [isLoadingMonth, setIsLoadingMonth] = useState(false);
    const fetchedMonths = useRef<Set<string>>(new Set());
    // Maps empty month keys to the number of 150 ms revisit flashes already shown (max 3).
    const emptyMonthVisits = useRef<Map<string, number>>(new Map());

    const applyPage = (page: EventsPage) => {
        setEvents(page.results);
        setNextPageUrl(page.next);
        setPrevPageUrl(page.previous);
        setTotalCount(page.count);
    };

    const { selected: selectedTags, toggle: toggleTag, clear: clearTags } = useToggleSet<TagId>([]);
    const { selected: selectedTowns, toggle: toggleTown, clear: clearTowns } = useToggleSet<TownId>([]);

    const fetchEvents = async () => {
        setIsLoading(true);
        setCurrentWindow('3months');
        setNextPageUrl(null);
        setPrevPageUrl(null);
        setCurrentPage(1);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
        const category = selectedCategoryRef.current ?? undefined;
        const key = eventCacheKey('3months', selectedCategoryRef.current);

        // Towns and categories are static — fetch them once per session.
        if (getCachedTowns() === null) getTowns().then(data => { setCachedTowns(data); setTowns(data); });
        if (getCachedCategories() === null) getCategories().then(data => { setCachedCategories(data); setCategories(data); });

        const cached = getCachedPage(key);
        if (cached) {
            applyPage(cached);
            setIsLoading(false);
            return;
        }
        const page = await getEvents({ category });
        setCachedPage(key, page);
        applyPage(page);
        setIsLoading(false);
    };

    // Background-fetches a single month and merges into state. No-op if already fetched.
    // Records months that came back empty so fetchMonth can flash the skeleton on revisits.
    const prefetchMonth = async (year: number, month: number) => {
        const key = `${year}-${String(month).padStart(2, '0')}`;
        if (fetchedMonths.current.has(key)) return;
        fetchedMonths.current.add(key);
        const after = new Date(year, month - 1, 1).toISOString();
        const before = new Date(year, month, 0, 23, 59, 59).toISOString();
        const { results } = await getEvents({ after, before });
        if (results.length === 0) emptyMonthVisits.current.set(key, 0);
        setEvents(prev => mergeEvents(prev, results));
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
        fetchEvents();
    }, [viewMode]);

    const setWindow = async (w: EventWindow) => {
        setNextPageUrl(null);
        setPrevPageUrl(null);
        setCurrentPage(1);
        const key = eventCacheKey(w, selectedCategoryRef.current);
        const cached = getCachedPage(key);
        if (cached) {
            applyPage(cached);
            setCurrentWindow(w);
            return;
        }
        setIsLoadingWindow(true);
        const page = await fetchForWindow(w, selectedCategoryRef.current ?? undefined);
        setCachedPage(key, page);
        applyPage(page);
        setCurrentWindow(w);
        setIsLoadingWindow(false);
    };

    const setCategory = (slug: string | null) => {
        selectedCategoryRef.current = slug;
        setSelectedCategoryState(slug);
        setCurrentWindow('3months');
        setNextPageUrl(null);
        setPrevPageUrl(null);
        setCurrentPage(1);
        fetchedMonths.current.clear();
        emptyMonthVisits.current.clear();
        const key = eventCacheKey('3months', slug);
        const cached = getCachedPage(key);
        if (cached) {
            applyPage(cached);
            return;
        }
        setIsLoading(true);
        getEvents({ category: slug ?? undefined }).then(page => {
            setCachedPage(key, page);
            applyPage(page);
            setIsLoading(false);
        });
    };

    const nextPage = async () => {
        if (!nextPageUrl || isLoadingPage) return;
        const key = eventCacheKey(currentWindow, selectedCategoryRef.current, nextPageUrl);
        const cached = getCachedPage(key);
        if (cached) {
            applyPage(cached);
            setCurrentPage(p => p + 1);
            return;
        }
        setIsLoadingPage(true);
        const page = await getEvents({ pageUrl: nextPageUrl });
        setCachedPage(key, page);
        applyPage(page);
        setCurrentPage(p => p + 1);
        setIsLoadingPage(false);
    };

    const prevPage = async () => {
        if (!prevPageUrl || isLoadingPage) return;
        const key = eventCacheKey(currentWindow, selectedCategoryRef.current, prevPageUrl);
        const cached = getCachedPage(key);
        if (cached) {
            applyPage(cached);
            setCurrentPage(p => p - 1);
            return;
        }
        setIsLoadingPage(true);
        const page = await getEvents({ pageUrl: prevPageUrl });
        setCachedPage(key, page);
        applyPage(page);
        setCurrentPage(p => p - 1);
        setIsLoadingPage(false);
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
        if (selectedCategoryRef.current !== null) {
            setCategory(null);
        }
    };

    const PAGE_SIZE = 30;
    const totalPages = Math.ceil(totalCount / PAGE_SIZE) || 1;

    return {
        filteredEvents,
        towns,
        categories,
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
            clearEventCache();
            if (currentWindow === '3months') {
                fetchEvents();
            } else {
                setIsLoading(true);
                setNextPageUrl(null);
                setPrevPageUrl(null);
                setCurrentPage(1);
                const key = eventCacheKey(currentWindow, selectedCategoryRef.current);
                fetchForWindow(currentWindow, selectedCategoryRef.current ?? undefined).then(page => {
                    setCachedPage(key, page);
                    applyPage(page);
                    setIsLoading(false);
                });
            }
        },
    };
}
