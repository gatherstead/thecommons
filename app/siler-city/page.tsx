'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '../../lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type Business = {
  id: number;
  name: string | null;
  description: string | null;
};

type BulletinPost = {
  id: number;
  title: string | null;
  org_name: string | null;
  details: string | null;
};

export default function SilerCityPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [posts, setPosts] = useState<BulletinPost[]>([]);

  useEffect(() => {
    async function fetchData() {
      const { data: bizData } = await supabase
        .from('businesses')
        .select('id, name, description')
        .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35')
        .limit(5);

      const { data: postData } = await supabase
        .from('bulletin_board_posts')
        .select('id, title, org_name, details')
        .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35')
        .limit(3);

      if (bizData) setBusinesses(bizData);
      if (postData) setPosts(postData);
    }

    fetchData();
  }, []);

  return (
    <main className="min-h-screen p-10 font-sans max-w-4xl mx-auto space-y-12">
      <h1 className="text-3xl font-bold">Welcome to Siler City</h1>
      <p className="text-lg text-gray-700">
        A historic railroad town with a walkable downtown and growing arts and food scene.
      </p>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Local Businesses</h2>
        <div className="grid gap-4">
          {businesses.map((biz) => (
            <Card key={biz.id}>
              <CardContent>
                <h3 className="text-lg font-bold">{biz.name}</h3>
                {biz.description && <p>{biz.description}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
        <Link href="/businesses" className="text-blue-600 underline block mt-4">
          View all businesses →
        </Link>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Community Bulletin Board</h2>
        <div className="grid gap-4">
          {posts.map((post) => (
            <Card key={post.id}>
              <CardContent>
                <h3 className="text-lg font-bold">{post.title}</h3>
                {post.org_name && <p className="text-sm text-gray-600">by {post.org_name}</p>}
                {post.details && <p className="mt-2">{post.details}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
        <Link href="/siler-city/bulletin-board" className="text-blue-600 underline block mt-4">
          See more bulletin board posts →
        </Link>
      </section>
    </main>
  );
}
