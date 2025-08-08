'use client';

import { useEffect, useState } from 'react';
import { supabase } from '../../lib/supabaseClient';

export default function SupabaseTestPage() {
  const [result, setResult] = useState<string>('Loading...');

  useEffect(() => {
    async function fetchData() {
      if (!supabase) {
        setResult('❌ Supabase client not initialized. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set.');
        return;
      }
      // Explicitly capture the non-null supabase client for TypeScript
      const client = supabase;

      const { data, error } = await client.from('businesses').select('*');
      if (error) {
        setResult(`❌ Error: ${error.message}`);
      } else {
        setResult(`✅ Connected! Found ${data.length} businesses.`);
      }
    }

    fetchData();
  }, []);

  return (
    <main style={{ padding: '40px', fontFamily: 'sans-serif' }}>
      <h1>Supabase Test</h1>
      <p>{result}</p>
    </main>
  );
}