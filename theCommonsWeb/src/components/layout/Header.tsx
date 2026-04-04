export function Header() {
    const today = new Date();
    const dateStr = today.toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
    });

    return (
        <header>
            <div className="max-w-300 mx-auto px-4 pt-5">

                <div className="border-t border-(--color-border) mt-2" />

                {/* ── Three-item banner row ────────────────────────────── */}
                <div className="flex items-center justify-between">
                    <span className="text-[12px] uppercase tracking-wider text-(--color-text-muted) shrink-0 pt-2">
                        Est. 2026
                    </span>

                    <h1
                        className="flex-1 text-center font-black tracking-tight leading-none mx-4"
                        style={{
                            fontSize: 'clamp(2.75rem, 8vw, 6rem)',
                            fontFamily: 'var(--font-headline)',
                        }}
                    >
                        The Commons
                    </h1>

                    <span className="text-[12px] text-(--color-text-muted) shrink-0 pt-2">
                        {dateStr}
                    </span>
                </div>

                {/* ── Tagline — floats above the banner row ─────────────── */}
                <p className="text-center text-[12px] uppercase tracking-[0.22em] text-(--color-text-muted) pb-1.5">
                    Your Town's Digital Gathering Place
                </p>

                {/* ── Rule ─────────────────────────────────────────────── */}
                <div className="border-t-2 border-(--color-border) mt-2" />

                {/* ── Quote ────────────────────────────────────────────── */}
                <p className="text-center italic text-sm py-2 text-(--color-text)">
                    &ldquo;Find your next excuse to stay local.&rdquo;
                </p>

                {/* ── Closing rule ─────────────────────────────────────── */}
                <div className="border-t border-(--color-border)" />

            </div>
        </header>
    );
}
