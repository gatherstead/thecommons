'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';
import { EventCard } from '@/components/ui/eventcard';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

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

export default function SilerCityPage() {
  const [events, setEvents] = useState<EventType[]>([]);
  const [groupedEvents, setGroupedEvents] = useState({
    thisWeek: [] as EventType[],
    nextWeek: [] as EventType[],
    later: [] as EventType[],
  });
  const [posts, setPosts] = useState<PostType[]>([]);
  const [businesses, setBusinesses] = useState<BusinessType[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventType | null>(null);

  // Fetch data from Supabase
  useEffect(() => {
    async function fetchData() {
      if (!supabase) {
        setError(
          'Supabase client not initialized. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.'
        );
        return;
      }

      try {
        const { data: town, error: townError } = await supabase
          .from('towns')
          .select('id')
          .eq('slug', 'siler-city')
          .single();

        if (townError || !town) throw new Error('Siler City not found');

        const [eventsRes, postsRes, businessesRes] = await Promise.all([
          supabase.from('events').select('*').eq('town_id', town.id).order('start_time'),
          supabase.from('bulletin_board_posts').select('*').eq('town_id', town.id),
          supabase
            .from('businesses_with_tags')
            .select('*')
            .eq('town_id', town.id)
            .order('name'),
        ]);

        if (eventsRes.error || postsRes.error || businessesRes.error) {
          throw new Error(
            eventsRes.error?.message ||
            postsRes.error?.message ||
            businessesRes.error?.message ||
            'Unknown error'
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
  }, []);

  // Group events into "This Week", "Next Week", "Later"
  useEffect(() => {
    if (!events || events.length === 0) return;

    const now = new Date();
    const startOfWeek = new Date(now);
    startOfWeek.setDate(now.getDate() - now.getDay());
    startOfWeek.setHours(0, 0, 0, 0);

    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);
    endOfWeek.setHours(23, 59, 59, 999);

    const nextWeekStart = new Date(endOfWeek);
    nextWeekStart.setDate(endOfWeek.getDate() + 1);
    nextWeekStart.setHours(0, 0, 0, 0);

    const nextWeekEnd = new Date(nextWeekStart);
    nextWeekEnd.setDate(nextWeekStart.getDate() + 6);
    nextWeekEnd.setHours(23, 59, 59, 999);

    const grouped = { thisWeek: [] as EventType[], nextWeek: [] as EventType[], later: [] as EventType[] };

    events.forEach((event) => {
      const eventDate = new Date(event.start_time);
      if (eventDate >= startOfWeek && eventDate <= endOfWeek) grouped.thisWeek.push(event);
      else if (eventDate >= nextWeekStart && eventDate <= nextWeekEnd) grouped.nextWeek.push(event);
      else grouped.later.push(event);
    });

    setGroupedEvents(grouped);
  }, [events]);

  function truncate(text: string, maxLength = 120) {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  function renderEventGroup(title: string, events: EventType[], showHeader: boolean) {
    if (!events || events.length === 0) return null;
    return (
      <div className="mb-8">
        {showHeader && <h3 className="text-xl font-heading font-semibold text-primary mb-4">{title}</h3>}
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {events.map((event) => (
            <EventCard key={event.id} event={event} onClick={() => setSelectedEvent(event)} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">Siler City</h1>
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

        {/* Events Tab Content */}
        <TabsContent value="events">
          <section className="py-6">
            <h2 className="sr-only">Upcoming Events</h2>
            {(() => {
              const groups = groupedEvents;
              const nonEmptyGroups = [groups.thisWeek, groups.nextWeek, groups.later].filter((g) => g.length > 0);
              const showHeader = nonEmptyGroups.length > 1;

              return (
                <>
                  {renderEventGroup('This Week', groups.thisWeek, showHeader)}
                  {renderEventGroup('Next Week', groups.nextWeek, showHeader)}
                  {renderEventGroup('Later', groups.later, showHeader)}
                  {nonEmptyGroups.length === 0 && <p>No events to display.</p>}
                </>
              );
            })()}

            <div className="mt-6 text-center">
              <Link href="/siler-city/events" className="text-accent underline text-sm font-medium">
                View full events calendar →
              </Link>
            </div>

            {selectedEvent && (
              <Modal isOpen onClose={() => setSelectedEvent(null)} title={selectedEvent.title}>
                <div className="space-y-4 text-sm text-foreground max-h-[70vh] overflow-y-auto">
                  <p className="italic text-muted">{new Date(selectedEvent.start_time).toLocaleString()}</p>
                  <p className="whitespace-pre-line">
                    {selectedEvent.card_summary || selectedEvent.facebook_post || selectedEvent.description || 'No summary available.'}
                  </p>
                  {selectedEvent.cta_url && (
                    <a
                      href={selectedEvent.cta_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent underline flex items-center gap-1 mt-2"
                    >
                      🔗 Link
                    </a>
                  )}
                </div>
              </Modal>
            )}
          </section>
        </TabsContent>

        {/* Bulletin Board Tab Content */}
        <TabsContent value="bulletin-board">
          <section className="py-6">
            <h2 className="sr-only">Bulletin Board</h2>
            <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
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
            <div className="mt-6 text-center">
              <Link href="/siler-city/bulletin-board" className="text-accent underline text-sm font-medium">
                View full bulletin board →
              </Link>
            </div>
          </section>
        </TabsContent>

        {/* Business Directory Tab Content */}
        <TabsContent value="businesses">
          <section className="py-6">
            <h2 className="sr-only">Local Businesses</h2>
            <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
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
            <div className="mt-6 text-center">
              <Link href="/siler-city/businesses" className="text-accent underline text-sm font-medium">
                View full business directory →
              </Link>
            </div>
          </section>
        </TabsContent>
      </Tabs>

      {/* Bottom CTA */}
      <section className="bg-accent2/10 py-12 px-6 rounded-2xl mt-16 text-center shadow-md border border-primary/30">
        <h2 className="text-2xl font-heading text-primary mb-4">Have something to share with Siler City?</h2>
        <p className="text-md text-text mb-6 max-w-xl mx-auto">
          Events, job openings, news, local stories — we want to hear from you.
        </p>
        <button
          data-tally-open="wzAZlR"
          data-tally-layout="modal"
          data-tally-width="700"
          className="bg-accent text-white text-lg font-semibold px-6 py-3 rounded hover:bg-accent/90 transition"
        >
          📝 Submit a Post
        </button>
      </section>

      <footer className="border-t pt-6 mt-16 text-sm text-subtle text-center">
        © 2025 The Commons · Built by Common Engine Studio
      </footer>
    </main>
  );
}
