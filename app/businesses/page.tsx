'use client';

import { useEffect, useState } from 'react';
import { supabase } from '../../lib/supabaseClient';
import { Card, CardContent } from '@/components/ui/card';

// Define the business type
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

export default function BusinessesPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchBusinesses() {
      const { data, error } = await supabase.from('businesses').select('*');
      if (error) {
        setError(error.message);
      } else {
        setBusinesses(data);
      }
    }

    fetchBusinesses();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Local Businesses</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}
      <div className="grid gap-6">
        {businesses.map((biz) => (
          <Card key={biz.id}>
            <CardContent className="p-4 space-y-2">
              <h2 className="text-xl font-bold">{biz.name}</h2>
              {biz.address && (
                <p className="text-sm text-gray-700">
                  {biz.address}, {biz.city} {biz.zip}
                </p>
              )}
              {biz.website && (
                <a
                  href={biz.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  {biz.website}
                </a>
              )}
              {biz.social_media && (
                <p className="text-sm text-gray-600">
                  Social: {biz.social_media}
                </p>
              )}
              {biz.description && <p className="text-gray-800">{biz.description}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabaseClient';
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

export default function BusinessesPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchBusinesses() {
      const { data, error } = await supabase.from('businesses').select('*');
      if (error) {
        setError(error.message);
      } else {
        setBusinesses(data);
      }
    }

    fetchBusinesses();
  }, []);

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Local Business Directory</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}
      <div className="grid gap-6">
        {businesses.map((biz) => (
          <Card key={biz.id}>
            <CardContent className="p-4 space-y-2">
              <h2 className="text-xl font-bold">{biz.name}</h2>
              {biz.address && (
                <p className="text-sm text-gray-700">
                  {biz.address}, {biz.city} {biz.zip}
                </p>
              )}
              {biz.website && (
                <a
                  href={biz.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  {biz.website}
                </a>
              )}
              {biz.social_media && (
                <p className="text-sm text-gray-600">
                  Social: {biz.social_media}
                </p>
              )}
              {biz.description && <p className="text-gray-800">{biz.description}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
