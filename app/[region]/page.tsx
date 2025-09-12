// app/[region]/page.tsx
// ----------------------
// Async Server Component for Region Page
// Fetches towns and events server-side for faster rendering and full TypeScript support.
// Notes:
// - Tabs and EventCard rendering are still compatible with client interactivity
// - Modal can be converted to a client component if needed
// - This avoids the 'PageProps' TypeScript error from client-only type
// ----------------------

import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

type Props = {
  params: {
    region: string;
  };
};

type TownType = {
  id: string;
  name: string;
  slug: string;
  description?: string;
  status: 'active' | 'passive';
};

type EventType = {
  id: string;
  title: string;
  description?: string;
  start_time: string;
};

// ----------------------
// Async Server Component
// ----------------------
export default async function RegionPage({ params }: Props) {
  const { region } = params;

  // ----------------------
  // Fetch region ID
  // ----------------------
  const { data: regionData, error: regionError } = await supabase
    .from('regions')
    .select('id')
    .eq('slug', region)
    .single();
  if (regionError || !regionData) return <p>Region not found</p>;
  const regionId = regionData.id;

  // ----------------------
  // Fetch towns in this region
  // ----------------------
  const { data: townsData, error: townsError } = await supabase
    .from('towns')
    .select('*')
    .eq('region_id', regionId)
    .order('status', { ascending: false });
  if (townsError) return <p>Error loading towns: {townsError.message}</p>;
  const towns = townsData || [];

  // ----------------------
  // Fetch events in all towns
  // ----------------------
  const townIds = towns.map(t => t.id);
  const { data: eventsData, error: eventsError } = await supabase
    .from('events')
    .select('*')
    .in('town_id', townIds)
    .order('start_time', { ascending: true });
  if (eventsError) return <p>Error loading events: {eventsError.message}</p>;
  const events = eventsData || [];

  // ----------------------
  // Helper: truncate text
  // ----------------------
  function truncate(text: string, maxLength = 120) {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  // ----------------------
  // Render JSX
  // ----------------------
  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{region.replace('-', ' ')}</h1>
        <p className="text-lg text-subtle font-body max-w-prose mx-auto">
          Explore towns and events in the {region.replace('-', ' ')} region.
        </p>
      </header>

      <Tabs defaultValue="towns" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="towns">Towns</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
        </TabsList>

        <TabsContent value="towns">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 mt-6">
            {towns.map(town => (
              <Link key={town.id} href={`/${region}/${town.slug}`}>
                <Card
                  className={`p-5 border border-[#A7A7A2] bg-white shadow hover:shadow-md transition rounded-xl cursor-pointer ${
                    town.status !== 'active' ? 'opacity-60 pointer-events-none' : ''
                  }`}
                >
                  <CardContent>
                    <h3 className="text-xl font-display font-semibold text-primary mb-2">{town.name}</h3>
                    <p className="text-sm text-muted">{truncate(town.description || '')}</p>
                    {town.status === 'passive' && (
                      <span className="inline-block mt-3 text-xs font-semibold bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                        Coming Soon
                      </span>
                    )}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="events">
          <div className="space-y-4 mt-6">
            {events.length === 0 && <p>No events found.</p>}
            {events.map(event => (
              <EventCard key={event.id} event={event} onClick={() => { /* For client interactivity, wrap in client component */ }} />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
