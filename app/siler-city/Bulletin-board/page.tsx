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

type BulletinPost = {
  id: number;
  title: string;
  org_name: string;
  cta_type: string;
  cta_destination: string;
  details: string;
  cost: string | null;
  start_date: string | null;
  end_date: string | null;
};

export default function SilerCityPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [posts, setPosts] = useState<BulletinPost[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      const bizResponse = await supabase.from('businesses').select('*').eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35');
      const postResponse = await supabase.from('bulletin_board_posts').select('*').eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35');

      if (bizResponse.error || postResponse.error) {
        setError(bizResponse.error?.message || postResponse.error?.message || 'Error fetching data');
      } else {
        setBusinesses(bizResponse.data);
        setPosts(postResponse.data);
      }
    }

    fetchData();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto space-y-10">
      <h1 className="text-3xl font-bold mb-4">Siler City: Local Highlights</h1>

      {error && <p className="text-red-500">❌ {error}</p>}

      <section>
        <h2 className="text-2xl font-semibold mb-2">Business Directory</h2>
        <div className="grid gap-4">
          {businesses.map((biz) => (
            <Card key={biz.id}>
              <CardContent>
                <h3 className="text-lg font-bold">{biz.name}</h3>
                <p className="text-sm text-gray-600">{biz.address}</p>
                {biz.website && (
                  <a className="text-blue-600 underline" href={biz.website} target="_blank" rel="noopener noreferrer">
                    Visit website
                  </a>
                )}
                <p className="text-sm">{biz.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-2">Bulletin Board</h2>
        <div className="grid gap-4">
          {posts.map((post) => (
            <Card key={post.id}>
              <CardContent>
                <h3 className="text-lg font-bold">{post.title}</h3>
                <p className="text-sm text-gray-700">{post.org_name}</p>
                <p className="text-sm">{post.details}</p>
                {post.cost && <p className="text-sm italic">Cost: {post.cost}</p>}
                {post.start_date && <p className="text-sm">📅 {post.start_date} – {post.end_date}</p>}
                {post.cta_destination && (
                  <a
                    href={post.cta_destination}
                    className="text-blue-600 underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {post.cta_type === 'learn_more' ? 'Learn more' :
                      post.cta_type === 'visit_website' ? 'Visit website' :
                      post.cta_type === 'email_us' ? 'Email us' :
                      'More info'}
                  </a>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}
