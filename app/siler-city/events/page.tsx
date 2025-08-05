'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { EventCard } from '@/components/ui/eventcard';

export default function EventsPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEvents() {
      const { data, error } = await supabase
        .from('events')
        .select('*')
        .eq('approved', true)
        .order('start_time', { ascending: true });

      if (error) {
        setError(error.message);
      } else {
        setEvents(data);
      }
    }

    fetchEvents();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Upcoming Events</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}

      <div className="grid gap-6">
        {events.map((event) => (
          <EventCard key={event.id} event={event} variant="expanded" />
        ))}
      </div>
    </main>
  );
}
