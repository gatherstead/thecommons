import { createElement, type ReactElement, type ReactNode } from 'react';
import { render, renderHook, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom/vitest';

// A QueryClient tuned for tests: retries off so error-path assertions resolve
// immediately instead of hanging on TanStack Query's retry backoff.
export function makeTestQueryClient(): QueryClient {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: Infinity },
            mutations: { retry: false },
        },
    });
}

function wrapper(client: QueryClient) {
    return function QueryWrapper({ children }: { children: ReactNode }) {
        return createElement(QueryClientProvider, { client }, children);
    };
}

// Renders a component inside a fresh QueryClientProvider. Returns the RTL result
// plus the client so tests can inspect or seed the cache.
export function renderWithClient(ui: ReactElement, options?: RenderOptions) {
    const client = makeTestQueryClient();
    return { client, ...render(ui, { wrapper: wrapper(client), ...options }) };
}

// renderHook variant with the same fresh-client wrapper for query/mutation hooks.
export function renderHookWithClient<Result, Props>(
    hook: (props: Props) => Result,
    options?: { initialProps?: Props },
) {
    const client = makeTestQueryClient();
    return { client, ...renderHook(hook, { wrapper: wrapper(client), ...options }) };
}
