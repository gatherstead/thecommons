// Module-level, in-memory cache for fetched event data.
//
// Lives outside the React tree on purpose: a useRef inside a hook is destroyed
// when its component unmounts (e.g. navigating away from the home page), so the
// cache would reset on every route change. A module singleton instead persists
// for the lifetime of the browser tab and is only dropped on a hard reload —
// matching the "in-memory, session-fresh" caching policy.

import type { EventsPage } from './eventService';
import type { TownOption, CategoryOption } from '../models/eventsModels';

const pageCache = new Map<string, EventsPage>();
let townsCache: TownOption[] | null = null;
let categoriesCache: CategoryOption[] | null = null;

// Identifies a list page by the request shape: time window + category, plus the
// pagination URL for paged results (empty for the first page of a view).
export function eventCacheKey(window: string, category: string | null, pageUrl?: string | null): string {
    return `${window}|${category ?? ''}|${pageUrl ?? ''}`;
}

export function getCachedPage(key: string): EventsPage | undefined {
    return pageCache.get(key);
}

export function setCachedPage(key: string, page: EventsPage): void {
    pageCache.set(key, page);
}

export function getCachedTowns(): TownOption[] | null {
    return townsCache;
}

export function setCachedTowns(towns: TownOption[]): void {
    townsCache = towns;
}

export function getCachedCategories(): CategoryOption[] | null {
    return categoriesCache;
}

export function setCachedCategories(categories: CategoryOption[]): void {
    categoriesCache = categories;
}

// Drops every cached page and the static lists. Call after a mutation (create /
// edit / delete) so the next read pulls fresh data from the backend.
export function clearEventCache(): void {
    pageCache.clear();
    townsCache = null;
    categoriesCache = null;
}
