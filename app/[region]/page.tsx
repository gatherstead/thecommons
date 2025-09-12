// app/[region]/page.tsx
// ----------------------
// Server component: fetches data for the region page
// ----------------------

import React from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import RegionTowns from './RegionTowns';
import RegionEvents from './RegionEvents';

// ----------------------
// Props typing
// ----------------------
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

export default async function RegionPage({ params }: Props) {
  const { region } = params;

  // ----------------------
  // Server data fetching
  // ----------------------
  let towns: TownType[] = [];
  let events: EventType[] = [];
  let error: string | null = null;

  try {
    const { data: regionData, error: regionError } = await supabase
      .from('regions')
      .select('id')
      .eq('slug', region)
      .single();
    if (regionError || !regionData) throw new Error('Region not found');

    const { data: townsData, error: townsError } = await supabase
      .from('towns')
      .select('*')
      .eq('region_id', regionData.id)
      .order('status', { ascending: false });
    if (townsError) throw townsError;

    const townIds = (townsData || []).map(t => t.id);
    const { data: eventsData, error: eventsError } = await supabase
      .from('events')
      .select('*')
      .in('town_id', townIds)
      .order('start_time', { ascending: true });
    if (eventsError) throw eventsError;

    towns = townsData || [];
    events = eventsData || [];
  } catch (err: any) {
    error = err.message;
  }

  // ----------------------
  // Render
  // ----------------------
  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{region.replace('-', ' ')}</h1>
        <p className="text-lg text-subtle font-body max-w-prose mx-auto">
          Explore towns and events in the {region.replace('-', ' ')} region.
        </p>
      </header>

      {error && <p className="text-red-500">❌ {error}</p>}

      <Tabs defaultValue="towns" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="towns">Towns</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
        </TabsList>

        <TabsContent value="towns">
          {/* ----------------------
              Client component: interactive towns UI
          ---------------------- */}
          <RegionTowns towns={towns} regionSlug={region} />
        </TabsContent>

        <TabsContent value="events">
          {/* ----------------------
              Client component: interactive events UI
          ---------------------- */}
          <RegionEvents events={events} />
        </TabsContent>
      </Tabs>
    </main>
  );
}
