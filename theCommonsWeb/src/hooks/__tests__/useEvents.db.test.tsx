import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { BackendEvent, PaginatedBackendEvents } from '@/models/eventsModels';
import { renderHookWithClient } from '../../../vitest.setup';
import { useEvents } from '../useEvents';

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
            return { ok: true, json: async () => page(EVENTS) } as Response;
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
    it('toggling a town filters the rendered list client-side', async () => {
        const { result } = renderHookWithClient(() => useEvents());

        await waitFor(() => expect(result.current.filteredEvents).toHaveLength(2));

        act(() => result.current.toggleTown('Carrboro'));

        expect(result.current.filteredEvents).toHaveLength(1);
        expect(result.current.filteredEvents[0].town).toBe('Carrboro');
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
});
