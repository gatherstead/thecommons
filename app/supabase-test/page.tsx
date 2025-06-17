'use client';

import { useEffect, useState } from 'react';
import { supabase } from '../../lib/supabaseClient';

export default function SupabaseTestPage() {
  const [result, setResult] = useState<string>('Loading...');

  useEffect(() => {
    async function fetchData() {
      const { data, error } = await supabase.from('businesses').select('*');
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


