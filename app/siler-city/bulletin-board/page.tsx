
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
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    org_name: '',
    details: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchPosts();
  }, []);

  async function fetchPosts() {
    const { data } = await supabase
      .from('bulletin_board_posts')
      .select('id, title, org_name, details')
      .eq('town_id', '5e02b672-7264-4069-8869-106c9f5fcd35');

    if (data) setPosts(data);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const { error } = await supabase
        .from('bulletin_board_posts')
        .insert([
          {
            title: formData.title,
            org_name: formData.org_name,
            details: formData.details,
            town_id: '5e02b672-7264-4069-8869-106c9f5fcd35'
          }
        ]);

      if (error) {
        console.error('Error creating post:', error);
        alert('Error creating post. Please try again.');
      } else {
        // Reset form and hide it
        setFormData({ title: '', org_name: '', details: '' });
        setShowForm(false);
        // Refresh posts
        fetchPosts();
      }
    } catch (error) {
      console.error('Error:', error);
      alert('Error creating post. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  }

  return (
    <main className="min-h-screen p-10 font-sans max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Siler City Bulletin Board</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          {showForm ? 'Cancel' : 'Create New Post'}
        </button>
      </div>

      {showForm && (
        <Card className="mb-6">
          <CardContent className="p-6">
            <h2 className="text-xl font-semibold mb-4">Create New Post</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="title" className="block text-sm font-medium mb-1">
                  Post Title *
                </label>
                <input
                  type="text"
                  id="title"
                  name="title"
                  value={formData.title}
                  onChange={handleInputChange}
                  required
                  className="w-full p-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Enter post title"
                />
              </div>

              <div>
                <label htmlFor="org_name" className="block text-sm font-medium mb-1">
                  Organization Name
                </label>
                <input
                  type="text"
                  id="org_name"
                  name="org_name"
                  value={formData.org_name}
                  onChange={handleInputChange}
                  className="w-full p-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Your organization or business name"
                />
              </div>

              <div>
                <label htmlFor="details" className="block text-sm font-medium mb-1">
                  Post Details *
                </label>
                <textarea
                  id="details"
                  name="details"
                  value={formData.details}
                  onChange={handleInputChange}
                  required
                  rows={4}
                  className="w-full p-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Describe your post in detail"
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:bg-gray-400"
                >
                  {isSubmitting ? 'Creating...' : 'Create Post'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600"
                >
                  Cancel
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

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
