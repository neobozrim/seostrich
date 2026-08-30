import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Omni Self Improving v1',
  description: 'An agent that has memory, inspects its work and self-improves.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
