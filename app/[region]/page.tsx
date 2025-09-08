'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

/**
 * RegionPageClient Component
 *
 * Displays towns and events for a specific region.
 * Uses Next.js 15+ App Router conventions (params is a Promise).
 */
export default function RegionPageClient({
  params,
}: {
  params: Promise<{ region: string }>; // Params are now a Promise in Next.js 15+
}) {
  // Unwrap the Promise to get the actual params object
  const { region } = React.use(params);

  // ----------------------
  // State Declarations
  // ----------------------
  const [towns, setTowns] = useState<any[]>([]); // List of towns in the region
  const [events, setEvents] = useState<any[]>([]); // All events for the region's towns
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null); // Currently open modal event
  const [error, setError] = useState<string | null>(null); // Error handling

  // Filter state
  const [selectedTowns, setSelectedTowns] = useState<string[]>([]); // Town filters
  const [selectedTags, setSelectedTags] = useState<string[]>([]); // Tag filters
  const [selectedTime, setSelectedTime] = useState<string>('all'); // Time filters: all, weekday, weekend, this-week, next-week

  // ----------------------
  // Data Fetching
  // ----------------------
  useEffect(() => {
    async function fetchData() {
      try {
        // 1. Get region ID by slug
        const { data: regionData, error: regionError } = await supabase
          .from('regions')
          .select('id')
          .eq('slug', region)
          .single();

        if (regionError) throw regionError;
        if (!regionData) throw new Error('Region not found');

        // 2. Get all towns in this region
        const { data: townsData, error: townsError } = await supabase
          .from('towns')
          .select('*')
          .eq('region_id', regionData.id)
          .order('status', { ascending: false });

        if (townsError) throw townsError;

        const townIds = townsData.map(town => town.id);

        // 3. Get all events for these towns
        const { data: eventsData, error: eventsError } = await supabase
          .from('events')
          .select('*')
          .in('town_id', townIds)
          .order('start_time', { ascending: true });

        if (eventsError) throw eventsError;

        // 4. Update state
        setTowns(townsData || []);
        setEvents(eventsData || []);
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchData();
  }, [region]);

  // ----------------------
  // Utility Functions
  // ----------------------

  // Truncate long text to a max length
  const truncate = (text: string, maxLength = 120) =>
    text.length > maxLength ? text.slice(0, maxLength) + '…' : text;

  // Toggle an item in a string[] filter array
  const toggleFilter = (
    filterSetter: React.Dispatch<React.SetStateAction<string[]>>,
    value: string
  ) => {
    filterSetter(prev =>
      prev.includes(value) ? prev.filter(item => item !== value) : [...prev, value]
    );
  };

  // ----------------------
  // Filtered Events Computation
  // ----------------------
  const filteredEvents = events.filter(event => {
    const townMatch = selectedTowns.length === 0 || selectedTowns.includes(event.town_id);
    const tagMatch = selectedTags.length === 0 || selectedTags.some(tag => event.tags?.includes(tag));

    let timeMatch = true;
    if (selectedTime !== 'all') {
      const eventDate = new Date(event.start_time);
      const today = new Date();
      const dayOfWeek = eventDate.getDay();

      switch (selectedTime) {
        case 'weekday':
          timeMatch = dayOfWeek >= 1 && dayOfWeek <= 5;
          break;
        case 'weekend':
          timeMatch = dayOfWeek === 0 || dayOfWeek === 6;
          break;
        case 'this-week': {
          const startOfWeek = new Date(today);
          startOfWeek.setDate(today.getDate() - today.getDay());
          const endOfWeek = new Date(startOfWeek);
          endOfWeek.setDate(startOfWeek.getDate() + 7);
          timeMatch = eventDate >= startOfWeek && eventDate < endOfWeek;
          break;
        }
        case 'next-week': {
          const startOfNextWeek = new Date(today);
          startOfNextWeek.setDate(today.getDate() - today.getDay() + 7);
          const endOfNextWeek = new Date(startOfNextWeek);
          endOfNextWeek.setDate(startOfNextWeek.getDate() + 7);
          timeMatch = eventDate >= startOfNextWeek && eventDate < endOfNextWeek;
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
      {/* Header */}
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">
          {region.replace('-', ' ')}
        </h1>
        <p className="text-lg text-subtle font-body max-w-prose mx-auto">
          Explore towns and events in the {region.replace('-', ' ')} region.
        </p>
      </header>

      {/* Error Display */}
      {error && <p className="text-red-500">❌ {error}</p>}

      {/* Tabs for Towns and Events */}
      <Tabs defaultValue="towns" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="towns">Towns</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
        </TabsList>

        {/* Towns Tab */}
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
                    <h3 className="text-xl font-display font-semibold text-primary mb-2">
                      {town.name}
                    </h3>
                    <p className="text-sm text-muted">{truncate(town.description)}</p>
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

        {/* Events Tab */}
        <TabsContent value="events">
          <div className="space-y-4 mt-6">
            {/* Filters */}
            <div className="flex flex-wrap gap-4 mb-4">
              {/* Town Filters */}
              {towns.map(town => (
                <label key={town.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedTowns.includes(town.id)}
                    onChange={() => toggleFilter(setSelectedTowns, town.id)}
                  />
                  {town.name}
                </label>
              ))}

              {/* Tag Filters */}
              {['live-music', 'pet-friendly'].map(tag => (
                <label key={tag} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedTags.includes(tag)}
                    onChange={() => toggleFilter(setSelectedTags, tag)}
                  />
                  {tag.replace('-', ' ')}
                </label>
              ))}

              {/* Time Filters */}
              {['all', 'weekday', 'weekend', 'this-week', 'next-week'].map(time => (
                <label key={time} className="flex items-center gap-2">
                  <input
                    type="radio"
                    checked={selectedTime === time}
                    onChange={() => setSelectedTime(time)}
                  />
                  {time.replace('-', ' ')}
                </label>
              ))}
            </div>

            {/* Event Cards */}
            {filteredEvents.map(event => (
              <EventCard
                key={event.id}
                event={event}
                onClick={() => setSelectedEvent(event)}
              />
            ))}

            {/* Modal for selected event */}
            {selectedEvent && (
              <Modal
                isOpen={true}
                onClose={() => setSelectedEvent(null)}
                title={selectedEvent.title}
              >
                <div className="space-y-2">
                  <p>{selectedEvent.description}</p>
                  <p className="text-sm text-muted">
                    {new Date(selectedEvent.start_time).toLocaleString()}
                  </p>
                </div>
              </Modal>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
