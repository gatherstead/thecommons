import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BackendEvent, PaginatedBackendEvents } from '@/models/eventsModels';
import { renderHookWithClient } from '../../../vitest.setup';
import { useEvents, type ViewMode } from '../useEvents';

// useEvents reads/writes the URL via next/navigation (48.13). There's no real
// App Router context in vitest, so stub it: useSearchParams reflects a
// mutable module-level URLSearchParams (set per test via setUrlSearchParams),
// router.replace is a spy tests can assert against, and pathname is fixed at '/'.
let currentSearchParams = new URLSearchParams();
const routerReplace = vi.fn();

vi.mock('next/navigation', () => ({
    useRouter: () => ({ replace: routerReplace }),
    usePathname: () => '/',
    useSearchParams: () => currentSearchParams,
}));

function setUrlSearchParams(qs: string) {
    currentSearchParams = new URLSearchParams(qs);
}

function backendEvent(over: Partial<BackendEvent>): BackendEvent {
    return {
        uuid: 'e1',
        title: 'Show',
        town: 'Carrboro',
        venue: 'Cat’s Cradle',
        date: '2026-12-01T19:00:00Z',
        description: '',
        price: '0',
        tag_names: [],
        category_slugs: [],
        photo: null,
        link: '',
        is_verified: true,
        source_name: '',
        ...over,
    };
}

function page(results: BackendEvent[]): PaginatedBackendEvents {
    return { count: results.length, next: null, previous: null, results };
}

const EVENTS = [
    backendEvent({ uuid: 'a', town: 'Carrboro' }),
    backendEvent({ uuid: 'b', town: 'Durham' }),
];

let fetchMock: ReturnType<typeof vi.fn>;
const eventUrls: string[] = [];

beforeEach(() => {
    eventUrls.length = 0;
    currentSearchParams = new URLSearchParams();
    routerReplace.mockClear();
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/events/towns/')) {
            return { ok: true, json: async () => [] } as Response;
        }
        if (url.includes('/events/categories/')) {
            return { ok: true, json: async () => [] } as Response;
        }
        if (url.includes('/events')) {
            eventUrls.push(url);
            // Town/tag filtering is server-side now — mimic the backend's
            // ?town=&tag= narrowing so tests can assert on the filtered result.
            const params = new URL(url, 'http://localhost').searchParams;
            const towns = params.getAll('town');
            const tags = params.getAll('tag');
            const filtered = EVENTS.filter(e => {
                if (towns.length > 0 && !towns.includes(e.town)) return false;
                if (tags.length > 0 && !tags.every(t => (e.tag_names ?? []).includes(t))) return false;
                return true;
            });
            return { ok: true, json: async () => page(filtered) } as Response;
        }
        throw new Error(`Unmocked fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('useEvents', () => {
    it('toggling a town refetches server-side filtered by ?town=', async () => {
        const { result } = renderHookWithClient(() => useEvents());

        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));

        act(() => result.current.toggleTown('Carrboro'));

        await waitFor(() => {
            expect(eventUrls.some(u => u.includes('town=Carrboro'))).toBe(true);
        });
        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(1));
        expect(result.current.filteredEvents[0].town).toBe('Carrboro');
        expect(result.current.totalCount).toBe(1);
    });

    it('switching to the past window refetches with a changed query', async () => {
        const { result } = renderHookWithClient(() => useEvents());

        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));
        const initialCalls = eventUrls.length;
        expect(eventUrls.some(u => u.includes('window=past'))).toBe(false);

        act(() => result.current.setWindow('past'));

        await waitFor(() => {
            expect(eventUrls.length).toBeGreaterThan(initialCalls);
            expect(eventUrls.some(u => u.includes('window=past'))).toBe(true);
        });
    });

    it('preserves the selected window across a feed <-> calendar toggle', async () => {
        const { result, rerender } = renderHookWithClient(
            (viewMode: ViewMode) => useEvents(viewMode),
            { initialProps: 'feed' },
        );

        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));

        act(() => result.current.setWindow('12months'));
        expect(result.current.currentWindow).toBe('12months');

        rerender('calendar');
        rerender('feed');

        expect(result.current.currentWindow).toBe('12months');
    });

    it('changing category does not reset the selected window', async () => {
        const { result } = renderHookWithClient(() => useEvents());

        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));

        act(() => result.current.setWindow('6months'));
        expect(result.current.currentWindow).toBe('6months');

        act(() => result.current.setCategory('music'));

        expect(result.current.currentWindow).toBe('6months');
    });

    describe('URL round-tripping (48.13)', () => {
        it('seeds filter state from a pasted URL on first render', async () => {
            setUrlSearchParams('tag=weekends&tag=evenings&town=Carrboro&category=music&window=12months');
            const { result } = renderHookWithClient(() => useEvents());

            expect(result.current.selectedTags).toEqual(['weekends', 'evenings']);
            expect(result.current.selectedTowns).toEqual(['Carrboro']);
            expect(result.current.selectedCategory).toBe('music');
            expect(result.current.currentWindow).toBe('12months');

            await waitFor(() => expect(eventUrls.length).toBeGreaterThan(0));
            const url = eventUrls[0];
            expect(url).toContain('tag=weekends');
            expect(url).toContain('tag=evenings');
            expect(url).toContain('town=Carrboro');
            expect(url).toContain('category=music');
            // '12months' is expressed as a `before=` cutoff by fetchForWindow, not
            // a literal window= param (only 'past' passes window= through) — the
            // state itself is what we're asserting here.
            expect(url).toContain('before=');
        });

        it('writes filter changes back to the URL with router.replace (shallow), not push', async () => {
            const { result } = renderHookWithClient(() => useEvents());
            await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));
            routerReplace.mockClear();

            act(() => result.current.toggleTown('Carrboro'));

            await waitFor(() => expect(routerReplace).toHaveBeenCalled());
            const [lastUrl, lastOpts] = routerReplace.mock.calls.at(-1) ?? [];
            expect(lastUrl).toBe('/?town=Carrboro');
            expect(lastOpts).toEqual({ scroll: false });
        });

        it('omits default-valued filters from the URL', async () => {
            const { result } = renderHookWithClient(() => useEvents());
            await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));

            // No filters applied yet -> the bare path, not e.g. "/?window=3months".
            expect(routerReplace).toHaveBeenLastCalledWith('/', { scroll: false });
        });

        it('clearFilters clears the URL back to the bare path', async () => {
            setUrlSearchParams('town=Carrboro&category=music&window=12months');
            const { result } = renderHookWithClient(() => useEvents());
            await waitFor(() => expect(result.current.selectedTowns).toEqual(['Carrboro']));

            act(() => result.current.clearFilters());

            await waitFor(() => expect(routerReplace).toHaveBeenLastCalledWith('/', { scroll: false }));
            expect(result.current.selectedTowns).toEqual([]);
            expect(result.current.selectedCategory).toBeNull();
            expect(result.current.currentWindow).toBe('3months');
        });

        it('restores a page > 1 found in the URL by walking forward from page 1', async () => {
            const localFetch = vi.fn(async (input: RequestInfo | URL) => {
                const url = String(input);
                if (url.includes('/events/towns/') || url.includes('/events/categories/')) {
                    return { ok: true, json: async () => [] } as Response;
                }
                const params = new URL(url, 'http://localhost').searchParams;
                const page = params.get('page') ? Number(params.get('page')) : 1;
                if (page < 2) {
                    return {
                        ok: true,
                        json: async () => ({
                            count: 2,
                            next: 'http://localhost/events/?page=2',
                            previous: null,
                            results: [EVENTS[0]],
                        }),
                    } as Response;
                }
                return {
                    ok: true,
                    json: async () => ({
                        count: 2,
                        next: null,
                        previous: 'http://localhost/events/?page=1',
                        results: [EVENTS[1]],
                    }),
                } as Response;
            });
            vi.stubGlobal('fetch', localFetch);

            setUrlSearchParams('page=2');
            const { result } = renderHookWithClient(() => useEvents());

            await waitFor(() => expect(result.current.currentPage).toBe(2));
            await waitFor(() =>
                expect(result.current.filteredEvents.some(e => e.id === EVENTS[1].uuid)).toBe(true),
            );
        });
    });
});
