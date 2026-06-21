import { QueryClient } from '@tanstack/react-query';

function makeQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: Infinity,
                gcTime: Infinity,
                refetchOnWindowFocus: false,
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
