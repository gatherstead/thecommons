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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !content) return;

    setSubmitting(true);
    const { error } = await supabase.from('bulletin_board_posts').insert([
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
    if (!error) {
      setSuccess(true);
      setTitle('');
      setContent('');
      setAuthorName('');
      setAuthorEmail('');
      setCategory('');
    } else {
     console.error('Submission error:', JSON.stringify(error, null, 2));
    }
  };

  return (
    <Card>
      <CardContent>
        <h2 className="text-xl font-semibold mb-4">{location} Bulletin Board</h2>

        {success && <p className="text-green-600 mb-4">Your post was submitted!</p>}

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
