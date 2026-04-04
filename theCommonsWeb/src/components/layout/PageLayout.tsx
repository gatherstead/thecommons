import type { ReactNode } from 'react';

interface PageLayoutProps {
    header: ReactNode;
    sidebar: ReactNode;
    footer: ReactNode;
    children: ReactNode;
}

export function PageLayout({ header, sidebar, footer, children }: PageLayoutProps) {
    return (
        <div className="min-h-screen bg-[var(--color-bg)]">
            <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-0 focus:left-0 focus:z-50 focus:p-2 focus:bg-white focus:text-[var(--color-text)]">
                Skip to content
            </a>
            {header}
            <main id="main-content" className="max-w-[960px] mx-auto px-4 py-4">
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                    <div className="lg:col-span-1 border-r-0 lg:border-r border-[var(--color-border-light)] lg:pr-4">
                        {sidebar}
                    </div>
                    <section className="lg:col-span-3" aria-live="polite">
                        {children}
                    </section>
                </div>
            </main>
            {footer}
        </div>
    );
}
