import Link from 'next/link';

export default function EventNotFound() {
    return (
        <main id="main-content" className="max-w-[720px] mx-auto px-4 py-16 text-center">
            <p className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3">
                404
            </p>
            <h1
                className="font-black tracking-tight leading-none mb-3"
                style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
            >
                Event Not Found
            </h1>
            <p className="text-sm text-[var(--color-text-muted)] mb-6">
                This event may have been removed or the link is no longer valid.
            </p>
            <Link
                href="/"
                className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors"
            >
                &larr; Return to Feed
            </Link>
        </main>
    );
}
