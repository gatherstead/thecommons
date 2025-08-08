'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type BulletinPost = {
  id: string;
  title: string | null;
  submitter_name: string | null;
  content: string | null;
  category: string | null;
  cta_url: string | null;
};

export default function BulletinBoardPage() {
  const [posts, setPosts] = useState<BulletinPost[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPosts() {
      if (!supabase) {
        setError('Supabase client not initialized. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.');
        return;
      }
      // Explicitly capture the non-null supabase client for TypeScript
      const client = supabase;

      try {
        const { data: town, error: townError } = await client
          .from('towns')
          .select('id')
          .eq('slug', 'siler-city') // Hardcoded for now
          .single();

        if (townError || !town) throw new Error('Siler City not found');

        const { data, error } = await client
          .from('bulletin_board_posts')
          .select('*')
          .eq('town_id', town.id)
          .order('created_at', { ascending: false });

        if (error) {
          setError(error.message);
        } else {
          setPosts(data);
        }
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchPosts();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Siler City Bulletin Board</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}
      <div className="grid gap-6">
        {posts.map((post) => (
          <Card key={post.id}>
            <CardContent className="p-4 space-y-2">
              <h2 className="text-xl font-bold">{post.title}</h2>
              {post.submitter_name && (
                <p className="text-sm text-gray-600 italic">
                  Posted by {post.submitter_name}
                </p>
              )}
              {post.category && (
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                  {post.category}
                </p>
              )}
              {post.content && <p className="text-gray-800">{post.content}</p>}
              {post.cta_url && (
                <a
                  href={post.cta_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  Learn more
                </a>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
