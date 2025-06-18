'use client';

import { useEffect, useState } from 'react';
import { supabase } from '../../../lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type BulletinPost = {
  id: number;
  title: string | null;
  org_name: string | null;
  details: string | null;
};

export default function BulletinBoardPage() {
  const [posts, setPosts] = useState<BulletinPost[]>([]);

  useEffect(() => {
    async function fetchPosts() {
      const { data } = await supabase
        .from('bulletin_board_posts')
        .select('id, title, org_name, details')
        .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35');

      if (data) setPosts(data);
    }

    fetchPosts();
  }, []);

  return (
    <main className="min-h-screen p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">Siler City Bulletin Board</h1>
      <div className="grid gap-6">
        {posts.map((post) => (
          <Card key={post.id}>
            <CardContent>
              <h2 className="text-xl font-semibold">{post.title}</h2>
              {post.org_name && <p className="text-sm text-gray-600">by {post.org_name}</p>}
              {post.details && <p className="mt-2">{post.details}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
