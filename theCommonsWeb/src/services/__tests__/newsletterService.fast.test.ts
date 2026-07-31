import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { subscribe, getSubscription, updateSubscription } from '../newsletterService';

const API_BASE = 'http://127.0.0.1:8000';

function jsonResponse(body: unknown, init?: { ok?: boolean; status?: number }) {
    return {
        ok: init?.ok ?? true,
        status: init?.status ?? 200,
        json: async () => body,
    } as Response;
}

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

function calledInit(): RequestInit {
    return fetchMock.mock.calls[0][1] as RequestInit;
}

describe('subscribe', () => {
    it('POSTs to the no-trailing-slash endpoint with email + frequency', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ email: 'a@b.com', frequency: 'WEEKLY' }));

        const result = await subscribe({ email: 'a@b.com', frequency: 'WEEKLY' });

        expect(calledUrl()).toBe(`${API_BASE}/newsletter/subscribe`);
        expect(calledInit().method).toBe('POST');
        expect(JSON.parse(calledInit().body as string)).toEqual({ email: 'a@b.com', frequency: 'WEEKLY' });
        expect(result).toEqual({ email: 'a@b.com', frequency: 'WEEKLY' });
    });

    it('surfaces the backend error message on 400', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ error: 'email is required' }, { ok: false, status: 400 }));

        await expect(subscribe({ email: '', frequency: 'WEEKLY' })).rejects.toThrow('email is required');
    });
});

describe('getSubscription', () => {
    it('GETs the manage endpoint with the token as a query param', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ email: 'a@b.com', frequency: 'MONTHLY', is_active: true }));

        const result = await getSubscription('tok-123');

        expect(calledUrl()).toBe(`${API_BASE}/newsletter/manage?token=tok-123`);
        expect(result).toEqual({ email: 'a@b.com', frequency: 'MONTHLY', is_active: true });
    });

    it('throws a NOT_FOUND error on 404', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ error: 'Unknown or invalid token.' }, { ok: false, status: 404 }));

        await expect(getSubscription('bad-token')).rejects.toThrow('NOT_FOUND');
    });
});

describe('updateSubscription', () => {
    it('PATCHes the manage endpoint with the new frequency', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ email: 'a@b.com', frequency: 'NEVER', is_active: false }));

        const result = await updateSubscription('tok-123', { frequency: 'NEVER' });

        expect(calledUrl()).toBe(`${API_BASE}/newsletter/manage?token=tok-123`);
        expect(calledInit().method).toBe('PATCH');
        expect(JSON.parse(calledInit().body as string)).toEqual({ frequency: 'NEVER' });
        expect(result).toEqual({ email: 'a@b.com', frequency: 'NEVER', is_active: false });
    });
});
