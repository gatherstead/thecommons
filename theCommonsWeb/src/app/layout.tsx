import type { Metadata } from 'next';
import { QueryProvider } from '../components/providers/QueryProvider';
import { AuthProvider } from '../hooks/useAuth';
import { MessageStackProvider } from '../hooks/useMessageStack';
import { SiteChrome } from '../components/layout/SiteChrome';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://thecommons.town'),
  title: 'The Commons - Community Events',
  description:
    'Find local events in your town. The Commons connects neighbors and supports local community.',
  verification: {
    google: 'REPLACE_WITH_CODE_FROM_GSC',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <AuthProvider>
            <MessageStackProvider>
              <SiteChrome>{children}</SiteChrome>
            </MessageStackProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
