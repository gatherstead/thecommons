'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';
import { Modal } from '@/components/ui/Modal';
import { BulletinPostForm } from '@/components/BulletinPostForm';
import { Card, CardContent } from '@/components/ui/card';


export default function SilerCityPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [events, setEvents] = useState<any[]>([]);
  const [posts, setPosts] = useState<any[]>([]);
  const [businesses, setBusinesses] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const now = new Date().toISOString();
        const nextWeek = new Date();
        nextWeek.setDate(nextWeek.getDate() + 7);
        const weekLater = nextWeek.toISOString();

        const [eventsRes, postsRes, businessesRes] = await Promise.all([
          supabase.from('events').select('*').gte('start_time', now).lte('start_time', weekLater).order('start_time'),
          supabase.from('bulletin_board_posts').select('*').order('start_date'),
          supabase.from('businesses').select('*').order('name'),
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
            .gt('start_time', weekLater)
            .order('start_time')
            .limit(5 - eventsData.length);
          if (!extended.error) {
            eventsData = [...eventsData, ...extended.data];
          }
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

  return (
    <main className="min-h-screen px-4 py-10 font-sans max-w-4xl mx-auto space-y-12">
      <h1 className="text-3xl font-bold mb-2">Siler City</h1>
      <p className="text-gray-600">Explore what’s happening this week.</p>

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
        <div className="flex justify-between items-center mb-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="bg-blue-600 text-white px-4 py-1.5 rounded hover:bg-blue-700 text-sm"
          >
            Add a Post
          </button>
        </div>
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
        <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Add a Post">
          <BulletinPostForm location="Siler City" />
        </Modal>
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
    </main>
  );
}
