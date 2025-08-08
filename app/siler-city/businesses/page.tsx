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
  website_url: string | null;
  instagram_url: string | null;
  description: string | null;
  tag_slugs: string[];
};

const TAG_NAME_LOOKUP: Record<string, string> = {
  'pet-friendly': 'Pet-Friendly',
  'live-music': 'Live Music',
  'merchants-association': 'Merchants Association',
  'spanish-speaking': 'Spanish Speaking',
  'accessible': 'Accessible',
};

export default function SilerCityBusinessesPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchBusinesses() {
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
          .eq('slug', 'siler-city') // Hardcoded for Siler City
          .single();

        if (townError || !town) throw new Error('Siler City not found');

        const { data, error } = await client
          .from('businesses_with_tags') // Assuming this view/table exists and includes tag_slugs
          .select('*')
          .eq('town_id', town.id)
          .order('name');

        if (error) {
          setError(error.message);
        } else {
          setBusinesses(data);
        }
      } catch (err: any) {
        setError(err.message);
      }
    }

    fetchBusinesses();
  }, []);

  function truncate(text: string, maxLength = 120): string {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  return (
    <main className="p-10 font-sans max-w-4xl mx-auto">
      <h1 className="text-3xl font-semibold mb-6">Siler City Local Businesses</h1>
      {error && <p className="text-red-500 mb-4">❌ {error}</p>}
      <div className="grid gap-6 sm:grid-cols-2 md:grid-cols-3">
        {businesses.map((biz) => {
          const tagNames = (biz.tag_slugs || [])
            .map((slug: string) => TAG_NAME_LOOKUP[slug])
            .filter(Boolean);

          return (
            <Card
              key={biz.id}
              className="border border-subtle bg-white shadow-sm hover:shadow-md transition rounded-xl"
            >
              <CardContent className="p-4 space-y-2 min-h-[10rem]">
                <h2 className="text-xl font-bold">{biz.name}</h2>
                {biz.description && (
                  <p className="text-sm text-foreground min-h-[3.5rem]">
                    {truncate(biz.description)}
                  </p>
                )}
                {(biz.website_url || biz.instagram_url) && (
                  <div className="text-sm text-accent flex gap-4 mt-1">
                    {biz.website_url && (
                      <a
                        href={biz.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        Website
                      </a>
                    )}
                    {biz.instagram_url && (
                      <a
                        href={biz.instagram_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        Instagram
                      </a>
                    )}
                  </div>
                )}
                {tagNames.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tagNames.map((name: string) => (
                      <span
                        key={name}
                        className="text-xs font-medium bg-subtle text-text px-2 py-0.5 rounded-full shadow-sm"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </main>
  );
}
