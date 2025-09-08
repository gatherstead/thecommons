'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

type Props = {
  params: Promise<{ region: string; town: string }>;
};

type EventType = {
  id: string;
  title: string;
  description?: string;
  start_time: string;
};

export default function TownPage({ params }: Props) {
  const { region, town } = React.use(params); // unwrap params

  const [events, setEvents] = useState<EventType[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const { data: townData, error: townError } = await supabase
          .from('towns')
          .select('id')
          .eq('slug', town)
          .single();
        if (townError || !townData) throw new Error('Town not found');

        const { data: eventsData, error: eventsError } = await supabase
          .from('events')
          .select('*')
          .eq('town_id', townData.id)
          .order('start_time', { ascending: true });
        if (eventsError) throw eventsError;

        setEvents(eventsData || []);
      } catch (err: any) {
        setError(err.message);
      }
    }
    fetchData();
  }, [town]);

  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{town.replace('-', ' ')}</h1>
        <p className="text-base text-subtle font-body max-w-prose">
          Explore events in your community.
        </p>
      </header>

      {error && <p className="text-red-500">❌ {error}</p>}

      <Tabs defaultValue="events">
        <TabsList className="grid w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3">
          <TabsTrigger value="events">Events</TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          <div className="space-y-4 mt-6">
            {events.length === 0 && <p>No events to display.</p>}
            {events.map(event => (
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
