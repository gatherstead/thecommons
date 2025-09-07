// app/[region]/[town]/page.tsx
import { Suspense } from 'react';
import RegionTownPageClient from '@/components/RegionTownPageClient';

type ParamsType = {
  params: Promise<{ region: string; town: string }>;
};

export default async function TownPage({ params }: ParamsType) {
  const resolvedParams = await params;

  return (
    <Suspense fallback={<p>Loading {resolvedParams.town}...</p>}>
      <RegionTownPageClient region={resolvedParams.region} town={resolvedParams.town} />
    </Suspense>
  );
}
 