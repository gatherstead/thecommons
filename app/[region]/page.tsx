'use client';

import React from 'react';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

export default function RegionPageClient({ params }: { params: Promise<{ region: string }> }) {
  const resolvedParams = React.use(params);
  const { region } = resolvedParams;

  const [towns, setTowns] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const { data: regionData } = await supabase.from('regions').select('id').eq('slug', region).single();
        if (!regionData) throw new Error('Region not found');

        const townsRes = await supabase.from('towns').select('*').eq('region_id', regionData.id).order('status', { ascending: false });
        if (townsRes.error) throw townsRes.error;

        const townIds = townsRes.data.map(t => t.id);
        const eventsRes = await supabase.from('events').select('*').in('town_id', townIds);
        if (eventsRes.error) throw eventsRes.error;

        setTowns(townsRes.data);
        setEvents(eventsRes.data);
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchData();
  }, [region]);

  function truncate(text: string, maxLength = 120) {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  // Filters state
  const [selectedTowns, setSelectedTowns] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedTime, setSelectedTime] = useState<string>('all');
  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
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
                    <p className="text-sm text-muted">{truncate(town.description)}</p>
                    {town.status === 'passive' && <span className="inline-block mt-3 text-xs font-semibold bg-yellow-100 text-yellow-800 px-2 py-1 rounded">Coming Soon</span>}
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="events">
          <div className="space-y-4 mt-6">
            <div className="flex flex-wrap gap-4 mb-4">
              {/** Replace selects with checkboxes for filters **/}
              <div>
                <label className="font-semibold mr-2">Towns:</label>
                {['all', ...towns.map(t => t.id)].map((id) => (
                  <label key={id} className="inline-flex items-center mr-2">
                    <input type="checkbox" value={id} checked={selectedTowns.includes(id.toString()) || id === 'all'}
                      onChange={() => {
                        if(id === 'all') setSelectedTowns([]);
                        else setSelectedTowns(prev => prev.includes(id.toString()) ? prev.filter(x => x !== id.toString()) : [...prev, id.toString()]);
                      }} className="mr-1" />
                    {id === 'all' ? 'All' : towns.find(t => t.id === id)?.name}
                  </label>
                ))}
              </div>

              <div>
                <label className="font-semibold mr-2">Tags:</label>
                {['all', 'live-music', 'pet-friendly'].map(tag => (
                  <label key={tag} className="inline-flex items-center mr-2">
                    <input type="checkbox" value={tag} checked={selectedTags.includes(tag) || tag === 'all'}
                      onChange={() => {
                        if(tag === 'all') setSelectedTags([]);
                        else setSelectedTags(prev => prev.includes(tag) ? prev.filter(x => x !== tag) : [...prev, tag]);
                      }} className="mr-1" />
                    {tag === 'all' ? 'All' : tag.replace('-', ' ')}
                  </label>
                ))}
              </div>

              <div>
                <label className="font-semibold mr-2">Time:</label>
                {['all', 'weekday', 'weekend', 'this-week', 'next-week'].map(time => (
                  <label key={time} className="inline-flex items-center mr-2">
                    <input type="checkbox" value={time} checked={selectedTime === time}
                      onChange={() => setSelectedTime(time)} className="mr-1" />
                    {time === 'all' ? 'All Times' : time.replace('-', ' ')}
                  </label>
                ))}
              </div>
            </div>

            {/** Event cards **/}
            {events.filter(event => {
              // Implement filter logic based on selectedTowns, selectedTags, selectedTime
              return true; // placeholder
            }).map(event => <EventCard key={event.id} event={event} onClick={() => setSelectedEvent(event)} />)}

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
