import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

// Fonts
import { Fraunces, Public_Sans, Inter, IBM_Plex_Sans } from "next/font/google";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  style: ["normal", "italic"],
  variable: "--font-fraunces",
  display: "swap",
});

const publicSans = Public_Sans({
  subsets: ["latin"],
  variable: "--font-public-sans",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal"],
  variable: "--font-ibm",
  display: "swap",
});

export const metadata: Metadata = {
  title: "The Commons",
  description: "Connecting people to their local communities",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${publicSans.variable} ${inter.variable} ${ibmPlexSans.variable}`}
    >
      <body className="antialiased bg-background text-text font-body">
        {/* ✅ MailerLite Embed Script */}
        <Script
          id="mailerlite-embed"
          src="https://static.mailerlite.com/js/universal.js"
          strategy="afterInteractive"
        />

        {children}
      </body>
    </html>
  );
}
