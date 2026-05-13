import type { Metadata } from 'next';
import { AuthProvider } from '../hooks/useAuth';
import { Header } from '../components/layout/Header';
import { Footer } from '../components/layout/Footer';
import './globals.css';

export const metadata: Metadata = {
  title: 'The Commons - Community Events',
  description:
    'Find local events in your town. The Commons connects neighbors and supports local community.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <div className="min-h-screen bg-[var(--color-bg)]">
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-1 focus:bg-[var(--color-accent)] focus:text-white focus:text-sm"
            >
              Skip to content
            </a>
            <Header />
            {children}
            <Footer />
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
