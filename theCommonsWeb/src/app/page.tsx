import { dehydrate, HydrationBoundary } from '@tanstack/react-query';
import { getQueryClient } from '../lib/queryClient';
import { getEvents, getTowns, getCategories } from '../services/eventService';
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
      queryFn: () => getEvents({ category: undefined }),
    }),
    queryClient.prefetchQuery({ queryKey: ['towns'], queryFn: getTowns }),
    queryClient.prefetchQuery({ queryKey: ['categories'], queryFn: getCategories }),
  ]);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <HomePageClient />
    </HydrationBoundary>
  );
}
