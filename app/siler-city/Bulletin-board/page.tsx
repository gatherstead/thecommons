'use client';

import { useEffect, useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type Post = {
  id: string;
  title: string;
  org_name: string | null;
  cta_type: string;
  cta_destination: string;
  details: string | null;
  cost: string | null;
  start_date: string | null;
  end_date: string | null;
};

export default function BulletinBoard() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPosts() {
      const { data, error } = await supabase
        .from('bulletin_board_posts')
        .select('*')
        .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35') // Siler City UUID
        .order('start_date', { ascending: true });

      if (error) {
        setError(error.message);
      } else {
        setPosts(data);
      }
    }

    fetchPosts();
  }, []);

  const renderCTA = (post: Post) => {
    const { cta_type, cta_destination } = post;

    if (cta_type === 'visit_website' || cta_type === 'learn_more') {
      return (
        <a
          href={cta_destination}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-600 underline"
        >
          {cta_type === 'visit_website' ? 'Visit Website' : 'Learn More'}
        </a>
      );
    }

    if (cta_type === 'email_us') {
      return (
        <a href={`mailto:${cta_destination}`} className="text-blue-600 underline">
          Email Us
        </a>
      );
    }

    return null;
  };

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Community Bulletin Board</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}
      <div className="grid gap-6">
        {posts.map((post) => (
          <Card key={post.id}>
            <CardContent className="p-4 space-y-2">
              <h2 className="text-xl font-bold">{post.title}</h2>
              {post.org_name && <p className="text-sm text-gray-700">By {post.org_name}</p>}
              {post.start_date && (
                <p className="text-sm text-gray-600">
                  {post.start_date}
                  {post.end_date ? ` – ${post.end_date}` : ''}
                </p>
              )}
              {post.cost && <p className="text-sm text-gray-600">Cost: {post.cost}</p>}
              {post.details && <p className="text-gray-800">{post.details}</p>}
              <div>{renderCTA(post)}</div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
