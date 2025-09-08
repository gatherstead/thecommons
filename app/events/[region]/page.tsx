// app/events/[region]/page.tsx
import Link from 'next/link';
import { supabase } from '@/lib/supabaseClient';

type Props = {
  params: { region: string }; // slug from URL
};

type TownType = {
  id: string;
  slug: string;
  name: string;
};

export default async function RegionPage({ params }: Props) {
  const { region: regionSlug } = params;

  // 1️⃣ Fetch the region to get its ID
  const { data: regionData, error: regionError } = await supabase
    .from('regions')
    .select('id, name')
    .eq('slug', regionSlug)
    .single();

  if (regionError || !regionData) {
    console.error('Error fetching region:', regionError?.message || 'Region not found');
    return <p className="text-red-500">❌ Failed to load region.</p>;
  }

  // 2️⃣ Fetch towns in this region by region.id
  const { data: townsData, error: townsError } = await supabase
    .from('towns')
    .select('slug, name')
    .eq('region_id', regionData.id)
    .order('name');

  if (townsError) {
    console.error('Error fetching towns:', townsError.message);
    return <p className="text-red-500">❌ Failed to load towns.</p>;
  }

  const towns: TownType[] = townsData || [];

  return (
    <main className="p-6">
      <h1 className="text-3xl font-bold">{regionData.name}</h1>
      {towns.length === 0 ? (
        <p>No towns found in this region.</p>
      ) : (
        <ul className="mt-4 list-disc list-inside">
          {towns.map((town) => (
            <li key={town.slug}>
              <Link href={`/events/${regionSlug}/${town.slug}`} className="text-accent underline">
                {town.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
