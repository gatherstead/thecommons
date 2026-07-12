import type { MetadataRoute } from 'next';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';
const SITE = 'https://thecommons.town';

async function fetchAllEventIds(): Promise<{ id: string; date: Date }[]> {
  const results: { id: string; date: Date }[] = [];
  let url: string | null = `${API_BASE}/events/`;
  while (url) {
    const res: Response = await fetch(url, { next: { revalidate: 3600 } });
    if (!res.ok) break;
    const data = await res.json();
    for (const e of data.results) {
      results.push({ id: e.uuid, date: new Date(e.date) });
    }
    url = data.next ?? null;
  }
  return results;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const events = await fetchAllEventIds().catch(() => []);
  const now = new Date();

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, lastModified: now, changeFrequency: 'daily', priority: 1.0 },
    { url: `${SITE}/about`, lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
  ];

  const eventRoutes: MetadataRoute.Sitemap = events.map(e => ({
    url: `${SITE}/events/${e.id}`,
    lastModified: e.date,
    changeFrequency: 'weekly',
    priority: 0.8,
  }));

  return [...staticRoutes, ...eventRoutes];
}
