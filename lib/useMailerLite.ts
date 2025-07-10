// lib/useMailerLite.ts

import { useEffect, useState } from 'react';

declare global {
  interface Window {
    ml?: (...args: any[]) => void;
  }
}

export function useMailerLite() {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && typeof window.ml === 'function') {
      setLoaded(true);
    }
  }, []);

  return loaded;
}
  