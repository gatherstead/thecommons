'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';

type Town = {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: 'active' | 'passive' | 'hidden';
};

export default function HomePage() {
  const [towns, setTowns] = useState<Town[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTowns() {
      const { data, error } = await supabase
        .from('towns')
        .select('*')
        .neq('status', 'hidden');
      if (error) {
        setError(error.message);
      } else {
        setTowns(data);
      }
    }

    fetchTowns();
  }, []);

  return (
    <main className="min-h-screen p-10 font-sans max-w-5xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">Welcome to The Commons</h1>
      <p className="mb-8 text-gray-700">
        Explore towns in the Haw River Region and discover what makes each one unique.
      </p>

      {error && <p className="text-red-500 mb-4">❌ {error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
        {towns.map((town) => (
          <Link key={town.id} href={`/${town.slug}`}>
            <div
              className={`rounded-xl p-4 border shadow hover:shadow-md transition ${
                town.status === 'passive' ? 'opacity-60 pointer-events-none' : 'bg-white'
              }`}
            >
              <h2 className="text-xl font-semibold mb-2">{town.name}</h2>
              <p className="text-sm text-gray-700">{town.description}</p>
              {town.status === 'passive' && (
                <span className="inline-block mt-3 text-xs font-semibold bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                  Coming Soon
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
