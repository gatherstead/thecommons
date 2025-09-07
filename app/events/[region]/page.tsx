// app/events/[region]/page.tsx
import Link from 'next/link';

type Params = {
  params: {
    region: string;
  };
};

export default async function RegionPage({ params }: Params) {
  const { region } = params;

  // Optionally fetch towns in this region from Supabase
  // const towns = await supabase.from('towns').select('*').eq('region_slug', region);

  const towns = ['siler-city']; // placeholder for now

  return (
    <main className="p-6">
      <h1 className="text-3xl font-bold">{region.replace('-', ' ')}</h1>
      <ul className="mt-4 list-disc list-inside">
        {towns.map((town) => (
          <li key={town}>
            <Link href={`/events/${region}/${town}`} className="text-accent underline">
              {town.replace('-', ' ')}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
