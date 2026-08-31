import type { Metadata, Viewport } from 'next';
import { Mulish, IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google';
import './globals.css';

// SEOstrich typography (OFL 1.1): Mulish 800 for display, IBM Plex Sans for body,
// IBM Plex Mono for data. See design-assets/HANDOVER.md.
const displayFont = Mulish({
  subsets: ['latin'],
  weight: '800',
  variable: '--font-display',
});

const bodyFont = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-body',
});

const monoFont = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'SEOstrich',
  description: 'An SEO agent that has memory, inspects its work and self-improves.',
  manifest: '/site.webmanifest',
  icons: {
    icon: [
      { url: '/icons/seostrich-favicon.svg', type: 'image/svg+xml' },
      { url: '/icons/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/icons/favicon-16.png', sizes: '16x16', type: 'image/png' },
    ],
    apple: '/icons/apple-touch-icon-180.png',
  },
};

export const viewport: Viewport = {
  themeColor: '#6B4226',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${bodyFont.variable} ${monoFont.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
