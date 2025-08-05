'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type BulletinPost = {
  id: number;
  title: string | null;
  submitter_name: string | null;
  content: string | null;
  category: string | null;
  cta_url: string | null;
};

export default function BulletinBoardPage() {
  const [posts, setPosts] = useState<BulletinPost[]>([]);

  useEffect(() => {
    async function fetchPosts() {
      const { data } = await supabase
        .from('bulletin_board_posts')
        .select('id, title, submitter_name, content, category, cta_url')
        .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35')
        .order('created_at', { ascending: false });

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
            <CardContent className="space-y-2">
              <h2 className="text-xl font-semibold text-primary">{post.title}</h2>
              {post.category && (
                <p className="text-xs uppercase text-subtle font-semibold">{post.category}</p>
              )}
              {post.submitter_name && (
                <p className="text-sm text-muted italic">by {post.submitter_name}</p>
              )}
              {post.content && <p className="text-sm text-foreground">{post.content}</p>}
              {post.cta_url && (
                <a
                  href={post.cta_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent underline block text-sm"
                >
                  Learn more →
                </a>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
