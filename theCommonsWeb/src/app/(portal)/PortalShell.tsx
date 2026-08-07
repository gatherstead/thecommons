import Image from 'next/image';

export function PortalShell({
    heading,
    subheading,
    children,
}: {
    heading?: string;
    subheading?: string;
    children: React.ReactNode;
}) {
    return (
        <div className="portal-page relative min-h-screen w-full overflow-x-hidden">
            <div aria-hidden className="portal-art overflow-hidden">
                {/* object-position X is the horizontal framing knob: higher %
                    slides the visible window right through the painting,
                    cutting more off the left of the tree. The asset is cut
                    wide on purpose so this has ~23vw of travel — see
                    docs/login-art.md.

                    The image is height-bound under object-cover (its render
                    height already matches the container), so there's no
                    vertical slack to slide through on its own. scale-y-[118%]
                    stretches the painting taller — a deliberate distortion,
                    the tree reads slightly elongated — leaving horizontal
                    zoom untouched (that stays governed by object-position X
                    on the wide asset, see above). The stretch over-fills the
                    container by ~9% top and bottom; -translate-y-[5%] spends
                    part of that overflow to push the visible window up — more
                    roots/ground stay hidden below, less empty canvas above.
                    Keep |translate-y| at or under half of (scale-y - 100),
                    i.e. up to ~9% here, or the bottom edge exposes background
                    instead of painting. */}
                <Image
                    src="/login-tree.webp"
                    alt=""
                    fill
                    priority
                    sizes="(max-width: 768px) 100vw, 78vw"
                    className="scale-y-[118%] -translate-y-[8%] object-cover object-[95%_center]"
                />
            </div>

            <div className="relative grid min-h-screen grid-cols-1 md:grid-cols-[60%_1fr]">
                <div aria-hidden className="hidden md:block" />

                <div className="flex items-start px-6 pt-[40vh] pb-16 md:items-center md:px-0 md:pr-[6vw] md:py-16 md:pt-16">
                    <div className="w-full max-w-[440px]">
                        <h1
                            className="mb-0 leading-none tracking-tight"
                            style={{ fontSize: 'clamp(2.1rem, 3.4vw, 2.75rem)' }}
                        >
                            The Commons
                        </h1>
                        <div className="mt-4 border-t border-[var(--color-border)]" />
                        <p className="mt-3 italic text-[var(--color-text-muted)]">
                            Local happenings, small NC towns.
                        </p>

                        {(heading || subheading) && (
                            <header className="mt-8">
                                {heading && <h2 className="mb-1 text-2xl">{heading}</h2>}
                                {subheading && (
                                    <p className="text-sm italic text-[var(--color-text-muted)]">
                                        {subheading}
                                    </p>
                                )}
                            </header>
                        )}

                        <div className="mt-8">{children}</div>
                    </div>
                </div>
            </div>
        </div>
    );
}
