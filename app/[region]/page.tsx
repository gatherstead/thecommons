'use client'; // app/[region]/page.tsx

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

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
  location?: string;
  tags?: string[];
  card_summary?: string;
  facebook_post?: string;
  cta_url?: string;
};

export default function RegionPage({ params }: Props) {
  const { region } = params;

  const [towns, setTowns] = useState<TownType[]>([]);
  const [events, setEvents] = useState<EventType[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventType | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ----------------------
  // Fetch data on mount
  // ----------------------
  useEffect(() => {
    async function fetchData() {
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

        setTowns(townsData || []);
        setEvents(eventsData || []);
      } catch (err: any) {
        setError(err.message);
      }
    }
    fetchData();
  }, [region]);

  function truncate(text: string, maxLength = 120) {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">
          {region.replace('-', ' ')}
        </h1>
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
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 mt-6">
            {towns.map((town) => (
              <Link key={town.id} href={`/${region}/${town.slug}`}>
                <Card
                  className={`p-5 border border-[#A7A7A2] bg-white shadow hover:shadow-md transition rounded-xl cursor-pointer ${
                    town.status !== 'active' ? 'opacity-60 pointer-events-none' : ''
                  }`}
                >
                  <CardContent>
                    <h3 className="text-xl font-display font-semibold text-primary mb-2">
                      {town.name}
                    </h3>
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
            {events.map((event) => (
              <EventCard key={event.id} event={event} onClick={() => setSelectedEvent(event)} />
            ))}

            {selectedEvent && (
              <Modal isOpen={true} onClose={() => setSelectedEvent(null)} title={selectedEvent.title}>
                <div className="space-y-2">
                  <p>{selectedEvent.description}</p>
                  <p className="text-sm text-muted">{new Date(selectedEvent.start_time).toLocaleString()}</p>
                </div>
              </Modal>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
