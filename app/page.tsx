'use client';

import Link from 'next/link';

export default function Home() {
  return (
    <main className="min-h-screen p-10 font-sans max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-4">Welcome to The Commons</h1>
      <p className="mb-6">
        Discover local businesses, events, and community updates in Siler City and beyond.
      </p>
      <Link href="/businesses" className="text-blue-600 underline">
        Browse the Business Directory →
      </Link>
    </main>
  );
}
