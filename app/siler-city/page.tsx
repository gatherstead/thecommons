'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type Business = {
  id: number;
  name: string | null;
  address: string | null;
  city: string | null;
  zip: string | null;
  website: string | null;
  social_media: string | null;
  description: string | null;
};

type Event = {
  id: number;
  name: string | null;
  date: string | null;
  location: string | null;
  description: string | null;
};

export default function SilerCityPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      const { data: bizData, error: bizError } = await supabase
        .from('businesses')
        .select('*');

      const { data: eventData, error: eventError } = await supabase
        .from('events')
        .select('*')
        .order('date', { ascending: true })
        .limit(5);

      if (bizError || eventError) {
        setError(bizError?.message || eventError?.message || 'Error loading data');
      } else {
        setBusinesses(bizData || []);
        setEvents(eventData || []);
      }
    }

    fetchData();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto space-y-10">
      <section>
        <h1 className="text-4xl font-bold mb-2">Welcome to Siler City</h1>
        <p className="text-lg text-gray-700">Explore all local businesses and upcoming events in one place.</p>
      </section>

      {error && <p className="text-red-500 mb-4">❌ {error}</p>}

      <section>
        <h2 className="text-2xl font-semibold mb-4">Local Businesses</h2>
        <div className="grid gap-6">
          {businesses.map((biz) => (
            <Card key={biz.id}>
              <CardContent className="space-y-2">
                <h3 className="text-xl font-bold">{biz.name}</h3>
                {biz.address && (
                  <p className="text-sm text-gray-700">
                    {biz.address}, {biz.city} {biz.zip}
                  </p>
                )}
                {biz.website && (
                  <a
                    href={biz.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 underline"
                  >
                    {biz.website}
                  </a>
                )}
                {biz.social_media && (
                  <p className="text-sm text-gray-600">Social: {biz.social_media}</p>
                )}
                {biz.description && <p className="text-gray-800">{biz.description}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Upcoming Events</h2>
        <div className="space-y-4">
          {events.map((event) => (
            <Card key={event.id}>
              <CardContent className="space-y-1">
                <h3 className="text-lg font-bold">{event.name}</h3>
                {event.date && (
                  <p className="text-sm text-gray-700">
                    📅 {new Date(event.date).toLocaleDateString()}
                  </p>
                )}
                {event.location && (
                  <p className="text-sm text-gray-600">📍 {event.location}</p>
                )}
                {event.description && (
                  <p className="text-sm text-gray-800">{event.description}</p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}