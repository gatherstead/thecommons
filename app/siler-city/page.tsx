'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

export default function SilerCityPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [posts, setPosts] = useState<any[]>([]);
  const [businesses, setBusinesses] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        // 1. Fetch Siler City town ID
        const { data: town, error: townError } = await supabase
          .from('towns')
          .select('id')
          .eq('slug', 'siler-city')
          .single();
  
        if (townError || !town) {
          console.error("❌ Could not fetch Siler City ID:", townError);
          throw new Error('Siler City not found');
        }
  
        console.log("✅ Siler City ID:", town.id);
  
        // 2. Set date range
        const now = new Date().toISOString();
        const nextWeek = new Date();
        nextWeek.setDate(nextWeek.getDate() + 7);
        const weekLater = nextWeek.toISOString();
  
        // 3. Fetch data from Supabase using town ID
        const [eventsRes, postsRes, businessesRes] = await Promise.all([
          supabase
            .from('events')
            .select('*')
            .eq('town_id', town.id)
            .gte('start_time', now)
            .lte('start_time', weekLater)
            .order('start_time'),
  
          supabase
            .from('bulletin_board_posts')
            .select('*')
            .eq('town_id', town.id),
  
          supabase
            .from('businesses')
            .select('*')
            .eq('town_id', town.id)
            .order('name'),
        ]);
  
        // 4. Log all results
        console.log("📆 Events Response:", eventsRes);
        console.log("📋 Posts Response:", postsRes);
        console.log("🏪 Businesses Response:", businessesRes);
  
        // 5. Check for any query errors
        if (eventsRes.error || postsRes.error || businessesRes.error) {
          throw new Error(
            eventsRes.error?.message ||
            postsRes.error?.message ||
            businessesRes.error?.message ||
            'Unknown error'
          );
        }
  
        // 6. Extend events if less than 5
        let eventsData = eventsRes.data;
        if (eventsData.length < 5) {
          const extended = await supabase
            .from('events')
            .select('*')
            .eq('town_id', town.id)
            .gt('start_time', weekLater)
            .order('start_time')
            .limit(5 - eventsData.length);
          if (!extended.error) {
            eventsData = [...eventsData, ...extended.data];
          }
        }
  
        // 7. Update state
        setEvents(eventsData);
        setPosts(postsRes.data);
        setBusinesses(businessesRes.data);
      } catch (err: any) {
        console.error("❌ fetchData error:", err.message);
        setError(err.message);
      }
    }
  
    fetchData();
  }, []);  

  function truncate(text: string, maxLength = 120): string {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  return (
    <main className="min-h-screen px-4 py-10 font-sans max-w-4xl mx-auto space-y-12">
      <h1 className="text-3xl font-bold mb-2">Siler City</h1>
      <p className="text-gray-600">
        Explore what’s happening in Siler City.{' '}
        <strong>
          <a
            href="https://tally.so/r/wzAZlR"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline"
          >
            Submit a post.
          </a>
        </strong>
      </p>

      {error && <p className="text-red-500">❌ {error}</p>}

      <section>
        <h2 className="text-2xl font-semibold mb-4">Upcoming Events</h2>
        <div className="space-y-4">
          {events.map(event => (
            <div key={event.id} className="p-4 bg-white rounded shadow">
              <h3 className="font-bold text-lg">{event.title}</h3>
              <p className="text-sm text-gray-600">{new Date(event.start_time).toLocaleString()}</p>
              <p>{truncate(event.description || '')}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Bulletin Board</h2>
        <div className="space-y-4">
          {posts.map(post => (
            <div key={post.id} className="p-4 bg-gray-50 rounded border border-gray-200">
              <h3 className="font-bold text-lg">{post.title}</h3>
              <p className="text-sm text-gray-600">{post.org_name}</p>
              <p className="text-sm text-gray-800">{truncate(post.details || '')}</p>
              <p className="text-sm text-gray-500">
                {post.cost || 'Free'}
                {post.start_date ? ` • ${new Date(post.start_date).toLocaleDateString()}` : ''}
              </p>
              {post.cta_type && post.cta_destination && (
                <a
                  href={post.cta_destination}
                  className="inline-block mt-2 text-blue-600 underline text-sm"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {post.cta_type === 'visit_website' ? 'Visit Website' :
                    post.cta_type === 'email_us' ? 'Email Us' :
                    'Learn More'}
                </a>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Local Businesses</h2>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {businesses.map(biz => (
            <Card key={biz.id}>
              <CardContent className="space-y-2">
                <h3 className="text-lg font-bold">{biz.name}</h3>
                <p className="text-sm text-gray-700">{biz.address}</p>
                <p className="text-sm text-gray-600">{biz.hours}</p>
                <p className="text-gray-800 text-sm">{truncate(biz.description || '')}</p>
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="mt-4">
          <Link href="/businesses" className="text-blue-600 underline">
            View full business directory →
          </Link>
        </div>
      </section>

      {/* BOTTOM SUBMIT BUTTON */}
      <section className="bg-blue-50 py-12 px-6 rounded-xl mt-16 text-center">
  <h2 className="text-2xl font-bold text-gray-800 mb-4">Have something to share with Siler City?</h2>
  <p className="text-gray-700 mb-6">Events, job openings, news, local stories — we want to hear from you.</p>
  <button
    data-tally-open="wzAZlR"
    data-tally-layout="modal"
    data-tally-width="700"
    data-tally-emoji-text="📝 Submit a Post"
    data-tally-emoji-animation="bounce"
    className="bg-blue-600 text-white text-lg font-semibold px-6 py-3 rounded hover:bg-blue-700 transition"
  >
    📝 Submit a Post
  </button>
</section>

    </main>
  );
}