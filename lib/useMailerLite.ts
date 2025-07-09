// lib/useMailerLite.ts

export function showMailerLitePopup(formId: string = '9UJ5al') {
    if (typeof window.ml === 'function') {
      window.ml('show', formId, true);
    } else {
      const interval = setInterval(() => {
        if (typeof window.ml === 'function') {
          window.ml('show', formId, true);
          clearInterval(interval);
        }
      }, 300);
    }
  }
  