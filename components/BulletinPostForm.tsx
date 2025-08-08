'use client';

import { useState } from 'react';
import { supabase } from '@/lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

type BulletinPostFormProps = {
  location: string;
};

export function BulletinPostForm({ location }: BulletinPostFormProps) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [authorName, setAuthorName] = useState('');
  const [authorEmail, setAuthorEmail] = useState('');
  const [category, setCategory] = useState('');
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null); // Added error state

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); // Clear previous errors
    if (!title || !content) {
      setError('Title and Content are required.');
      return;
    }

    if (!supabase) {
      setError('Supabase client not initialized. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.');
      return;
    }
    // Explicitly capture the non-null supabase client for TypeScript
    const client = supabase;

    setSubmitting(true);
    const { error: submitError } = await client.from('bulletin_board_posts').insert([
      {
        title,
        content,
        author_name: authorName || null,
        author_email: authorEmail || null,
        category: category || null,
        location,
      },
    ]);

    setSubmitting(false);
    if (!submitError) {
      setSuccess(true);
      setTitle('');
      setContent('');
      setAuthorName('');
      setAuthorEmail('');
      setCategory('');
    } else {
     console.error('Submission error:', JSON.stringify(submitError, null, 2));
     setError(`Submission failed: ${submitError.message}`); // Display error to user
    }
  };

  return (
    <Card>
      <CardContent>
        <h2 className="text-xl font-semibold mb-4">{location} Bulletin Board</h2>

        {success && <p className="text-green-600 mb-4">Your post was submitted!</p>}
        {error && <p className="text-red-500 mb-4">❌ {error}</p>} {/* Display error */}

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="Title*"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full p-2 border rounded"
            required
          />
          <textarea
            placeholder="Content*"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full p-2 border rounded"
            rows={5}
            required
          />
          <input
            type="text"
            placeholder="Your Name"
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
            className="w-full p-2 border rounded"
          />
          <input
            type="email"
            placeholder="Email (optional)"
            value={authorEmail}
            onChange={(e) => setAuthorEmail(e.target.value)}
            className="w-full p-2 border rounded"
          />
          <input
            type="text"
            placeholder="Category (e.g., Events, Items)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full p-2 border rounded"
          />

          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            {submitting ? 'Submitting…' : 'Submit Post'}
          </button>
        </form>
      </CardContent>
    </Card>
  );
}
