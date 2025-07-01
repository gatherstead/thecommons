'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

const TAG_NAME_LOOKUP: Record<string, string> = {
  'pet-friendly': 'Pet-Friendly',
  'live-music': 'Live Music',
  'merchants-association': 'Merchants Association',
  'spanish-speaking': 'Spanish Speaking',
  'accessible': 'Accessible',
  // Add more as needed
};

export default function SilerCityPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [posts, setPosts] = useState<any[]>([]);
  const [businesses, setBusinesses] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const { data: town, error: townError } = await supabase
          .from('towns')
          .select('id')
          .eq('slug', 'siler-city')
          .single();

        if (townError || !town) throw new Error('Siler City not found');

        const now = new Date().toISOString();
        const nextWeek = new Date();
        nextWeek.setDate(nextWeek.getDate() + 7);
        const weekLater = nextWeek.toISOString();

        const [eventsRes, postsRes, businessesRes] = await Promise.all([
          supabase
            .from('events')
            .select('*')
            .eq('town_id', town.id)
            .gte('start_time', now)
            .lte('start_time', weekLater)
            .order('start_time'),
          supabase.from('bulletin_board_posts').select('*').eq('town_id', town.id),
          supabase.from('businesses_with_tags').select('*').eq('town_id', town.id).order('name'),
        ]);

        if (eventsRes.error || postsRes.error || businessesRes.error) {
          throw new Error(
            eventsRes.error?.message ||
            postsRes.error?.message ||
            businessesRes.error?.message ||
            'Unknown error'
          );
        }

        let eventsData = eventsRes.data;
        if (eventsData.length < 5) {
          const extended = await supabase
            .from('events')
            .select('*')
            .eq('town_id', town.id)
            .gt('start_time', weekLater)
            .order('start_time')
            .limit(5 - eventsData.length);
          if (!extended.error) eventsData = [...eventsData, ...extended.data];
        }

        setEvents(eventsData);
        setPosts(postsRes.data);
        setBusinesses(businessesRes.data);
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchData();
  }, []);

  function truncate(text: string, maxLength = 120): string {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return `${date.toLocaleDateString('en-US')} ${date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    })}`;
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

      {/* Events */}
      <section>
        <h2 className="text-2xl font-display font-bold text-foreground mb-6">Upcoming Events</h2>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {events.map(event => (
            <Card key={event.id}>
              <CardContent className="space-y-2">
                <h3 className="text-lg font-semibold text-primary">{event.title}</h3>
                <p className="text-sm text-muted">{formatDate(event.start_time)}</p>
                <p className="text-sm text-foreground">{truncate(event.description || '')}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Bulletin Board */}
      <section>
        <h2 className="text-2xl font-display font-bold text-foreground mb-6">Bulletin Board</h2>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {posts.map(post => (
            <Card key={post.id}>
              <CardContent className="space-y-2">
                <h3 className="text-lg font-semibold text-primary">{post.title}</h3>
                {post.org_name && <p className="text-sm text-muted">{post.org_name}</p>}
                <p className="text-sm text-foreground">{truncate(post.details || '')}</p>
                <p className="text-sm text-subtle">
                  {post.cost || 'Free'}
                  {post.start_date ? ` • ${formatDate(post.start_date)}` : ''}
                </p>
                {post.cta_type && post.cta_destination && (
                  <a
                    href={post.cta_destination}
                    className="inline-block text-sm text-accent underline mt-1"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {post.cta_type === 'visit_website'
                      ? 'Visit Website'
                      : post.cta_type === 'email_us'
                        ? 'Email Us'
                        : 'Learn More'}
                  </a>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Business Directory */}
      <section>
        <h2 className="text-2xl font-display font-bold text-foreground mb-6">Local Businesses</h2>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {businesses.map(biz => {
            const tagNames = (biz.tag_slugs || [])
              .map((slug: string) => TAG_NAME_LOOKUP[slug])
              .filter(Boolean);

            return (
              <Card key={biz.id}>
                <CardContent className="space-y-2">
                  <h3 className="text-lg font-semibold text-primary">{biz.name}</h3>

                  {biz.description && (
                    <p className="text-sm text-foreground min-h-[3.5rem]">{truncate(biz.description)}</p>
                  )}


                  {(biz.website_url || biz.instagram_url) && (
                    <div className="text-sm text-accent flex gap-4 mt-1">
                      {biz.website_url && (
                        <a
                          href={biz.website_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          Website
                        </a>
                      )}
                      {biz.instagram_url && (
                        <a
                          href={biz.instagram_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline"
                        >
                          Instagram
                        </a>
                      )}
                    </div>
                  )}

                  {tagNames.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {tagNames.map(name => (
                        <span
                          key={name}
                          className="text-xs font-medium bg-[#F0F0EB] text-[#2B2B2B] px-2 py-0.5 rounded-full shadow-sm"
                        >
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
          <Link href="/businesses" className="text-accent underline text-sm font-medium">
            View full business directory →
          </Link>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="bg-[#7F9E5D]/10 py-12 px-6 rounded-2xl mt-16 text-center shadow-md border border-[#355E4C]/30">
        <h2 className="text-2xl font-heading text-primary mb-4">
          Have something to share with Siler City?
        </h2>
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
    </main>
  );
}
