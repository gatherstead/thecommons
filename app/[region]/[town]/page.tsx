'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

// Lookup for business tag names
const TAG_NAME_LOOKUP: Record<string, string> = {
  'pet-friendly': 'Pet-Friendly',
  'live-music': 'Live Music',
  'merchants-association': 'Merchants Association',
  'spanish-speaking': 'Spanish Speaking',
  'accessible': 'Accessible',
};

type EventType = {
  id: string;
  start_time: string;
  title: string;
  description?: string;
  card_summary?: string;
  facebook_post?: string;
  cta_url?: string;
};

type PostType = {
  id: string;
  title: string;
  submitter_name?: string;
  content?: string;
};

type BusinessType = {
  id: string;
  name: string;
  description?: string;
  website_url?: string;
  instagram_url?: string;
  tag_slugs?: string[];
};

type Props = {
  params: {
    region: string;
    town: string;
  };
};

export default function TownPage({ params }: Props) {
  // ----------------------
  // Unwrap params using React.use()
  // ----------------------
  const { region, town } = React.use(params);

  // ----------------------
  // Local state
  // ----------------------
  const [events, setEvents] = useState<EventType[]>([]);
  const [posts, setPosts] = useState<PostType[]>([]);
  const [businesses, setBusinesses] = useState<BusinessType[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventType | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ----------------------
  // Fetch data from Supabase
  // ----------------------
  useEffect(() => {
    async function fetchData() {
      try {
        // First, look up the town UUID by slug
        const { data: townData, error: townError } = await supabase
          .from('towns')
          .select('id, name')
          .eq('slug', town)
          .single();

        if (townError || !townData) throw new Error('Town not found');
        const townId = townData.id;

        // Fetch events, posts, and businesses by town UUID
        const [eventsRes, postsRes, businessesRes] = await Promise.all([
          supabase.from('events').select('*').eq('town_id', townId).order('start_time'),
          supabase.from('bulletin_board_posts').select('*').eq('town_id', townId),
          supabase.from('businesses_with_tags').select('*').eq('town_id', townId).order('name'),
        ]);

        if (eventsRes.error || postsRes.error || businessesRes.error) {
          throw new Error(
            eventsRes.error?.message || postsRes.error?.message || businessesRes.error?.message || 'Unknown error'
          );
        }

        setEvents(eventsRes.data);
        setPosts(postsRes.data);
        setBusinesses(businessesRes.data);
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchData();
  }, [town]);

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
      <header className="space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{town.replace('-', ' ')}</h1>
        <p className="text-base text-subtle font-body max-w-prose">
          Explore what’s happening in your community — businesses, events, and local stories.{' '}
          <a
            href="https://tally.so/r/wzAZlR"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent underline font-medium"
          >
            Submit a post
          </a>
          .
        </p>
      </header>

      {error && <p className="text-red-500">❌ {error}</p>}

      <Tabs defaultValue="events" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="bulletin-board">Bulletin Board</TabsTrigger>
          <TabsTrigger value="businesses">Businesses</TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 mt-6">
            {events.map((event) => (
              <EventCard key={event.id} event={event} onClick={() => setSelectedEvent(event)} />
            ))}
          </div>

          {selectedEvent && (
            <Modal isOpen={true} onClose={() => setSelectedEvent(null)} title={selectedEvent.title}>
              <div className="space-y-2">
                <p>{selectedEvent.description}</p>
                <p className="text-sm text-muted">{new Date(selectedEvent.start_time).toLocaleString()}</p>
              </div>
            </Modal>
          )}
        </TabsContent>

        <TabsContent value="bulletin-board">
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 mt-6">
            {posts.map((post) => (
              <Card key={post.id} className="border border-subtle bg-white shadow-sm hover:shadow-md transition rounded-xl">
                <CardContent className="space-y-2 min-h-[10rem]">
                  <h3 className="text-lg font-semibold text-primary">{post.title}</h3>
                  {post.submitter_name && <p className="text-sm text-muted italic">{post.submitter_name}</p>}
                  <p className="text-sm text-foreground">{truncate(post.content ?? '')}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="businesses">
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 mt-6">
            {businesses.map((biz) => {
              const tagNames = (biz.tag_slugs || []).map((slug) => TAG_NAME_LOOKUP[slug]).filter(Boolean);
              return (
                <Card key={biz.id} className="border border-subtle bg-white shadow-sm hover:shadow-md transition rounded-xl">
                  <CardContent className="space-y-2 min-h-[10rem]">
                    <h3 className="text-lg font-semibold text-primary">{biz.name}</h3>
                    {biz.description && <p className="text-sm text-foreground min-h-[3.5rem]">{truncate(biz.description)}</p>}
                    {(biz.website_url || biz.instagram_url) && (
                      <div className="text-sm text-accent flex gap-4 mt-1">
                        {biz.website_url && (
                          <a href={biz.website_url} target="_blank" rel="noopener noreferrer" className="underline">
                            Website
                          </a>
                        )}
                        {biz.instagram_url && (
                          <a href={biz.instagram_url} target="_blank" rel="noopener noreferrer" className="underline">
                            Instagram
                          </a>
                        )}
                      </div>
                    )}
                    {tagNames.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {tagNames.map((name) => (
                          <span key={name} className="text-xs font-medium bg-subtle text-text px-2 py-0.5 rounded-full shadow-sm">
                            {name}
                          </span>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
