'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

// ----------------------
// Props and Types
// ----------------------
type Props = {
  params: Promise<{
    region: string;
  }>;
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
  town_id: string;
  start_time: string;
  title: string;
  description?: string;
};

// ----------------------
// Component
// ----------------------
export default function RegionPageClient({ params }: Props) {
  // Unwrap the params promise (Next.js 15+)
  const { region } = React.use(params);

  // State
  const [towns, setTowns] = useState<TownType[]>([]);
  const [events, setEvents] = useState<EventType[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventType | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedTowns, setSelectedTowns] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedTime, setSelectedTime] = useState<'all' | 'weekday' | 'weekend' | 'this-week' | 'next-week'>('all');

  // ----------------------
  // Fetch data
  // ----------------------
  useEffect(() => {
    async function fetchData() {
      try {
        // Get region ID
        const { data: regionData } = await supabase
          .from('regions')
          .select('id')
          .eq('slug', region)
          .single();

        if (!regionData) throw new Error('Region not found');

        // Fetch towns
        const townsRes = await supabase
          .from('towns')
          .select('*')
          .eq('region_id', regionData.id)
          .order('status', { ascending: false });

        if (townsRes.error) throw townsRes.error;

        const townIds = townsRes.data.map((t: TownType) => t.id);

        // Fetch events for all towns in region
        const eventsRes = await supabase
          .from('events')
          .select('*')
          .in('town_id', townIds)
          .order('start_time', { ascending: true });

        if (eventsRes.error) throw eventsRes.error;

        setTowns(townsRes.data);
        setEvents(eventsRes.data);
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchData();
  }, [region]);

  // ----------------------
  // Utility: truncate text
  // ----------------------
  function truncate(text: string, maxLength = 120) {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  // ----------------------
  // Filter toggle helper
  // ----------------------
  const toggleFilter = (setter: React.Dispatch<React.SetStateAction<string[]>>, value: string) => {
    setter(prev => (prev.includes(value) ? prev.filter(item => item !== value) : [...prev, value]));
  };

  // ----------------------
  // Filtered events
  // ----------------------
  const filteredEvents = events.filter(event => {
    const townMatch = selectedTowns.length === 0 || selectedTowns.includes(event.town_id);
    const tagMatch = selectedTags.length === 0 || selectedTags.some(tag => event.tags?.includes(tag));

    let timeMatch = true;
    if (selectedTime !== 'all') {
      const eventDate = new Date(event.start_time);
      const dayOfWeek = eventDate.getDay();
      switch (selectedTime) {
        case 'weekday':
          timeMatch = dayOfWeek >= 1 && dayOfWeek <= 5;
          break;
        case 'weekend':
          timeMatch = dayOfWeek === 0 || dayOfWeek === 6;
          break;
        case 'this-week': {
          const now = new Date();
          const start = new Date(now);
          start.setDate(now.getDate() - now.getDay());
          const end = new Date(start);
          end.setDate(start.getDate() + 7);
          timeMatch = eventDate >= start && eventDate < end;
          break;
        }
        case 'next-week': {
          const now = new Date();
          const start = new Date(now);
          start.setDate(now.getDate() - now.getDay() + 7);
          const end = new Date(start);
          end.setDate(start.getDate() + 7);
          timeMatch = eventDate >= start && eventDate < end;
          break;
        }
      }
    }

    return townMatch && tagMatch && timeMatch;
  });

  // ----------------------
  // Render JSX
  // ----------------------
  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{region.replace('-', ' ')}</h1>
        <p className="text-lg text-subtle font-body max-w-prose mx-auto">Explore towns and events in the {region.replace('-', ' ')} region.</p>
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
                <Card className={`p-5 border border-[#A7A7A2] bg-white shadow hover:shadow-md transition rounded-xl cursor-pointer ${town.status !== 'active' ? 'opacity-60 pointer-events-none' : ''}`}>
                  <CardContent>
                    <h3 className="text-xl font-display font-semibold text-primary mb-2">{town.name}</h3>
                    <p className="text-sm text-muted">{town.description}</p>
                    {town.status === 'passive' && <span className="inline-block mt-3 text-xs font-semibold bg-yellow-100 text-yellow-800 px-2 py-1 rounded">Coming Soon</span>}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="events">
          <div className="space-y-4 mt-6">
            {filteredEvents.map((event) => (
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
