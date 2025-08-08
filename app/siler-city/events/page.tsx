'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type Event = {
  id: string;
  title: string | null;
  start_time: string | null;
  end_time: string | null;
  location: string | null;
  description: string | null;
  cta_url: string | null;
};

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchEvents() {
      if (!supabase) {
        setError('Supabase client not initialized. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.');
        return;
      }
      // Explicitly capture the non-null supabase client for TypeScript
      const client = supabase;

      try {
        const { data: town, error: townError } = await client
          .from('towns')
          .select('id')
          .eq('slug', 'siler-city') // Hardcoded now, dynamic later
          .single();

        if (townError || !town) throw new Error('Siler City not found');

        const { data, error } = await client
          .from('events')
          .select('*')
          .eq('town_id', town.id)
          .order('start_time');

        if (error) {
          setError(error.message);
        } else {
          setEvents(data);
        }
      } catch (err: any) {
        setError(err.message);
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
          <Card key={event.id}>
            <CardContent className="p-4 space-y-2">
              <h2 className="text-xl font-bold">{event.title}</h2>
              {event.start_time && (
                <p className="text-sm text-gray-700">
                  {new Date(event.start_time).toLocaleString()}
                </p>
              )}
              {event.location && (
                <p className="text-sm text-gray-600">{event.location}</p>
              )}
              {event.description && (
                <p className="text-gray-800">{event.description}</p>
              )}
              {event.cta_url && (
                <a
                  href={event.cta_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  Learn more
                </a>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
