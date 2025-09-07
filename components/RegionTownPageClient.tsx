"use client";
import React from 'react';
import Link from 'next/link';

type Props = {
  region: string;
  town: string;
};

export default function RegionTownPageClient({ region, town }: Props) {
  // Placeholder towns; can fetch from Supabase if needed
  const towns = ['siler-city'];

  return (
    <main className="min-h-screen bg-background text-text px-4 py-12 max-w-5xl mx-auto space-y-16">
      <header className="space-y-4">
        <h1 className="text-4xl font-display font-extrabold text-primary">{town.replace('-', ' ')}</h1>
        <p className="text-base text-subtle font-body max-w-prose">
          Explore events in {region.replace('-', ' ')}.
        </p>
      </header>

      <section className="mt-6">
        <ul>
          {towns.map((t) => (
            <li key={t}>
              <Link href={`/events/${region}/${t}`} className="text-accent underline">
                {t.replace('-', ' ')}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

