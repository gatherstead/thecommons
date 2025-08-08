'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

export function Header() {
  const pathname = usePathname();

  // Navigation links: Home is for exploring towns, Businesses is removed as it's now town-specific.
  const navLinks = [
    { name: 'Home', href: '/' },
  ];

  return (
    <header className="bg-background border-b border-subtle py-4 px-4 sm:px-6 lg:px-8 sticky top-0 z-40 shadow-sm">
      <div className="max-w-5xl mx-auto flex justify-between items-center">
        <Link href="/" className="text-2xl font-display font-extrabold text-primary">
          The Commons
        </Link>
        <nav>
          <ul className="flex space-x-6">
            {navLinks.map((link) => (
              <li key={link.name}>
                <Link
                  href={link.href}
                  className={cn(
                    'text-base font-heading font-medium transition-colors hover:text-accent',
                    pathname === link.href ? 'text-accent' : 'text-text'
                  )}
                >
                  {link.name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
