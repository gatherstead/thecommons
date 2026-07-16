import Link from 'next/link';
import { PortalShell } from '../PortalShell';

export default function ForgotPasswordPage() {
    return (
        <PortalShell>
            <p className="text-sm italic text-[var(--color-text-muted)] mb-6">
                Self-serve reset is coming soon.
            </p>

            <div className="space-y-6">
                <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
                    We&apos;re still building password reset by mail. In the meantime, The Commons
                    doesn&apos;t require a password to get back in &mdash; just enter your email on the
                    Sign In page and we&apos;ll let you straight through.
                </p>

                <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
                    Still stuck? Reach the Commons team and we&apos;ll sort it out by hand.
                </p>

                <div className="pt-2">
                    <Link
                        href="/signin"
                        className="inline-block font-[var(--font-sans)] cursor-pointer tracking-wide uppercase text-xs font-bold px-4 py-2.5 bg-[var(--color-text)] text-[var(--color-bg)] border-2 border-[var(--color-text)] hover:bg-[var(--color-accent)] hover:border-[var(--color-accent)] no-underline"
                    >
                        Back to Sign In
                    </Link>
                </div>
            </div>
        </PortalShell>
    );
}
