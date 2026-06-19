import { createElement, type ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeTestQueryClient } from '../../../vitest.setup';
import { AuthProvider, useAuth } from '../useAuth';
import { authClient } from '../../lib/auth-client';

vi.mock('../../lib/auth-client', () => ({
    authClient: {
        getSession: vi.fn(),
        signOut: vi.fn(),
        signIn: { email: vi.fn() },
    },
}));

const getSession = vi.mocked(authClient.getSession);

function wrapper({ children }: { children: ReactNode }) {
    const client = makeTestQueryClient();
    return createElement(
        QueryClientProvider,
        { client },
        createElement(AuthProvider, null, children),
    );
}

let fetchMock: ReturnType<typeof vi.fn>;

function setFetch(handler: (url: string) => Response | Promise<Response>) {
    fetchMock = vi.fn((input: RequestInfo | URL) => Promise.resolve(handler(String(input))));
    vi.stubGlobal('fetch', fetchMock);
}

afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
});

beforeEach(() => {
    getSession.mockResolvedValue({
        data: { user: { id: 'u1', email: 'session@x.com', name: 'Session Name' } },
    } as never);
});

describe('useAuth', () => {
    it('hydrates the Django profile on the happy path', async () => {
        setFetch(url => {
            if (url.includes('/api/auth/token')) {
                return { ok: true, json: async () => ({ token: 'jwt123' }) } as Response;
            }
            if (url.includes('/events/me/profile')) {
                return {
                    ok: true,
                    json: async () => ({
                        id: 'u1',
                        email: 'profile@x.com',
                        business_name: 'Biz Co',
                        user_type: 'BUSINESS',
                        has_password: true,
                    }),
                } as Response;
            }
            throw new Error(`Unmocked fetch: ${url}`);
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => expect(result.current.isInitializing).toBe(false));

        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.token).toBe('jwt123');
        expect(result.current.user).toMatchObject({
            email: 'profile@x.com',
            business_name: 'Biz Co',
            user_type: 'BUSINESS',
            hasPassword: true,
        });
    });

    it('stays logged out without throwing when the JWT fetch fails', async () => {
        setFetch(url => {
            if (url.includes('/api/auth/token')) {
                return { ok: false, status: 401, json: async () => ({}) } as Response;
            }
            throw new Error(`Unexpected fetch after failed token: ${url}`);
        });

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => expect(result.current.isInitializing).toBe(false));

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
        expect(result.current.token).toBeNull();
    });
});
