import { useEffect } from 'react';

export function useMailerLite() {
  useEffect(() => {
    const scriptId = 'ml-universal';
    if (document.getElementById(scriptId)) return;

    const script = document.createElement('script');
    script.id = scriptId;
    script.src = 'https://static.mailerlite.com/js/universal.js';
    script.async = true;
    script.type = 'text/javascript';
    document.body.appendChild(script);
  }, []);

  return function showMailerLite(formId?: string) {
    if (typeof window !== 'undefined' && window.ml) {
      window.ml('show', formId || '9UJ5al', true);
    } else {
      console.warn('MailerLite script not loaded yet.');
    }
  };
}
  