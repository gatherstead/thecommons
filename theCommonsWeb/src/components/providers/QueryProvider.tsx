'use client';

import dynamic from 'next/dynamic';
import { QueryClientProvider } from '@tanstack/react-query';
import { getQueryClient } from '../../lib/queryClient';

const ReactQueryDevtools = dynamic(
    () => import('@tanstack/react-query-devtools').then(m => m.ReactQueryDevtools),
    { ssr: false },
);

export function QueryProvider({ children }: { children: React.ReactNode }) {
    return (
        <QueryClientProvider client={getQueryClient()}>
            {children}
            {process.env.NODE_ENV === 'development' && <ReactQueryDevtools />}
        </QueryClientProvider>
    );
}
