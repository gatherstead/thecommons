// HomePage.tsx
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';
declare global {
  interface Window {
    ml: any;
  }
}

export default function HomePage() {
  const [towns, setTowns] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTowns() {
      const { data, error } = await supabase
        .from('towns')
        .select('*')
        .neq('status', 'hidden')
        .order('status', { ascending: true });
      if (error) setError(error.message);
      else setTowns(data);
    }

    fetchTowns();

    const script = document.createElement('script');
    script.src = 'https://static.mailerlite.com/js/universal.js';
    script.async = true;
    script.type = 'text/javascript';
    document.body.appendChild(script);
  }, []);

  function truncate(text: string, maxLength = 120): string {
    return text.length > maxLength ? text.slice(0, maxLength) + '…' : text;
  }

  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="text-center space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">The Commons</h1>
        <p className="text-lg text-subtle font-body max-w-prose mx-auto">
          A digital main street for North Carolina towns, starting with the Haw River Region.
        </p>
      </header>

      <section className="space-y-6">
  <h2 className="text-2xl font-display font-bold text-primary">About Us</h2>

  <p className="text-base font-body max-w-prose">
   Find your next excuse to stay local: events, businesses, and community. This is your town's Digital Commons, conveniently pushed to wherever you spend time online - Instagram, Facebook, and email, just to start. Explore the region and support your neighbors!
  </p>

  <p className="text-base italic text-subtle font-body max-w-prose">
   <b> No algorithms. No clickbait. Just good old-fashioned internet, like your momma used to make.</b>
  </p>
</section>

      <section className="space-y-6">
        <h2 className="text-2xl font-display font-bold text-primary">🏘️ Explore the Region</h2>
        {error && <p className="text-red-500">❌ {error}</p>}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
          {towns.map((town) => (
            <Link key={town.id} href={`/${town.slug}`}>
              <div
                className={`rounded-xl p-5 border border-[#A7A7A2] bg-white shadow transition duration-200 ease-in-out ${
                  town.status === 'active'
                    ? 'hover:shadow-md hover:scale-[1.02] transform cursor-pointer'
                    : 'opacity-60 pointer-events-none'
                }`}
              >
                <h3 className="text-xl font-display font-semibold text-primary mb-2">{town.name}</h3>
                <p className="text-sm text-muted">{truncate(town.description)}</p>
                {town.status === 'passive' && (
                  <span className="inline-block mt-3 text-xs font-semibold bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                    Coming Soon
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="bg-accent2/10 py-12 px-6 rounded-2xl text-center shadow-md border border-primary/30">
        <h2 className="text-2xl font-display font-bold text-primary mb-4">
          Stay in the loop with local updates
        </h2>
        <p className="text-base font-body mb-6 max-w-xl mx-auto">
          Get weekly highlights from your region—events, town launches, and new businesses. Just the good stuff.
        </p>
        <button
          onClick={() => window.ml && window.ml('show', '9UJ5al', true)}
          className="bg-accent text-white text-lg font-semibold px-6 py-3 rounded hover:bg-accent/90 transition"
        >
          📬 Join the mailing list
        </button>
        <div className="flex flex-col sm:flex-row sm:justify-center gap-4 mt-6 text-sm">
          <a
            href="https://www.instagram.com/thecommonshawriverregion"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            📸 Haw River Region Instagram →
          </a>
          <a
            href="https://www.instagram.com/thecommonssilercity"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            📸 Siler City Instagram →
          </a>
        </div>
      </section>

      <footer className="border-t pt-6 mt-16 text-sm text-subtle">
        © 2025 The Commons · Built by Common Engine Studio
      </footer>
    </main>
  );
}
