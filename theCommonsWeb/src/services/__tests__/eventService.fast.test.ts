import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getEvents, getMyEvents, getStagedEvent } from '../eventService';

const API_BASE = 'http://127.0.0.1:8000';

function jsonResponse(body: unknown, init?: { ok?: boolean; status?: number }) {
    return {
        ok: init?.ok ?? true,
        status: init?.status ?? 200,
        json: async () => body,
    } as Response;
}

const EMPTY_PAGE = { results: [], next: null, previous: null, count: 0 };

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

function calledUrl(): string {
    return String(fetchMock.mock.calls[0][0]);
}

describe('getEvents query-string construction', () => {
    beforeEach(() => {
        fetchMock.mockResolvedValue(jsonResponse(EMPTY_PAGE));
    });

    it('hits the bare events endpoint with no params', async () => {
        await getEvents();
        expect(calledUrl()).toBe(`${API_BASE}/events/`);
    });

    it('encodes before/after/category together', async () => {
        await getEvents({ after: '2026-01-01', before: '2026-02-01', category: 'music' });
        const url = new URL(calledUrl());
        expect(url.pathname).toBe('/events/');
        expect(url.searchParams.get('after')).toBe('2026-01-01');
        expect(url.searchParams.get('before')).toBe('2026-02-01');
        expect(url.searchParams.get('category')).toBe('music');
    });

    it('serializes include_past as the string "true"', async () => {
        await getEvents({ include_past: true });
        expect(new URL(calledUrl()).searchParams.get('include_past')).toBe('true');
    });

    it('passes the past window through', async () => {
        await getEvents({ window: 'past' });
        expect(new URL(calledUrl()).searchParams.get('window')).toBe('past');
    });

    it('uses pageUrl verbatim and ignores other params', async () => {
        const pageUrl = `${API_BASE}/events/?cursor=abc123`;
        await getEvents({ pageUrl, category: 'music' });
        expect(calledUrl()).toBe(pageUrl);
    });
});

describe('eventService error handling', () => {
    it('degrades getEvents to an empty page on a 5xx (errors swallowed by design)', async () => {
        fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));
        await expect(getEvents()).resolves.toEqual(EMPTY_PAGE);
    });

    it('surfaces an error from getMyEvents on a 4xx', async () => {
        fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 401 }));
        await expect(getMyEvents('tok')).rejects.toThrow('Failed to fetch your events');
    });

    it('surfaces an error from getStagedEvent on a 5xx', async () => {
        fetchMock.mockResolvedValue(jsonResponse({}, { ok: false, status: 500 }));
        await expect(getStagedEvent('tok', '7')).rejects.toThrow('Failed to fetch event details');
    });
});
