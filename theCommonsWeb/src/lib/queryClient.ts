import { QueryClient } from '@tanstack/react-query';

function makeQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 60 * 1000,
                gcTime: Infinity,
                refetchOnWindowFocus: true,
                refetchOnReconnect: false,
                retry: 1,
            },
        },
    });
}

let browserClient: QueryClient | undefined;

export function getQueryClient() {
    // Server render of client components must not share a cache across requests.
    if (typeof window === 'undefined') return makeQueryClient();
    return (browserClient ??= makeQueryClient());
}
