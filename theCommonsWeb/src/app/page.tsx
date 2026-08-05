import { Suspense } from 'react';
import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import { getQueryClient } from '../lib/queryClient';
import { getEvents, getTowns } from '../services/eventService';
import HomePageClient from './HomePageClient';

// Render per-request so the prefetch below hits Django's (Redis-cached) data on
// every load. Without this, Next statically prerenders `/` at build time and
// serves a frozen snapshot that never reflects the daily 04:00 ET ingestion.
export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const queryClient = getQueryClient();

  // Prefetch the three queries the home page renders on first paint, hitting
  // Django's Redis cache over loopback. Failures must NOT break SSR — if Django
  // is down the client falls back to its own fetch, so each prefetch is isolated.
  await Promise.allSettled([
    queryClient.prefetchQuery({
      queryKey: ['events', 'window', '3months', null],
      queryFn: () => getEvents(),
    }),
    queryClient.prefetchQuery({ queryKey: ['towns'], queryFn: getTowns }),
  ]);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      {/* useEvents() reads useSearchParams() to seed filter state from the URL
          (48.13) — Next requires that call site to sit under a Suspense
          boundary. The page is already `force-dynamic`, so this doesn't add a
          new static/dynamic distinction; it just satisfies the build. */}
      <Suspense fallback={null}>
        <HomePageClient />
      </Suspense>
    </HydrationBoundary>
  );
}
