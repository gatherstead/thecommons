import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy — The Commons',
  description: 'Privacy policy for The Commons and the Broadcast browser extension.',
};

export default function PrivacyPolicyPage() {
  return (
    <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
      <nav className="mb-6">
        <Link
          href="/"
          className="text-xs uppercase tracking-wider no-underline hover:text-[var(--color-accent)] transition-colors"
        >
          &larr; Back to Feed
        </Link>
      </nav>

      <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
        <h1
          className="font-black tracking-tight leading-none mb-2"
          style={{
            fontSize: 'clamp(2.25rem, 6vw, 3.5rem)',
            fontFamily: 'var(--font-headline)',
          }}
        >
          Privacy Policy
        </h1>
        <p className="text-sm italic text-[var(--color-text-muted)]">
          Last updated: June 23, 2026
        </p>
      </header>

      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          The Commons Website
        </h2>
        <p className="drop-cap leading-relaxed mb-4">
          The Commons is a community events aggregator for small towns in North
          Carolina. We collect only what is necessary to operate the service.
        </p>
        <p className="leading-relaxed mb-4">
          When you create an account, we store your email address and display
          name. When you submit an event, we store the details you provide. We
          do not sell your information, serve ads, or share your data with third
          parties except as required to operate the site (e.g., our hosting
          provider).
        </p>
        <p className="leading-relaxed">
          We use cookies solely to keep you logged in. We do not use tracking
          cookies or analytics that follow you across other sites.
        </p>
      </section>

      <div className="rule-thick mb-8" aria-hidden="true" />

      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          Broadcast Browser Extension
        </h2>
        <p className="leading-relaxed mb-4">
          The Commons Broadcast extension is an internal operator tool used to
          submit events to third-party community calendars. It is not a
          general-purpose extension and is not intended for public consumer use.
        </p>

        <div className="border-l-2 border-[var(--color-border)] pl-4 mb-4 space-y-4">
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              Data collected
            </p>
            <p className="text-sm leading-relaxed">
              None. The extension collects no personal information, does not
              track browsing activity, and does not read page content outside
              of tabs it opens.
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              How it works
            </p>
            <p className="text-sm leading-relaxed">
              When an operator initiates a manual review, the Broadcast console
              sends a structured recipe — event title, date, venue, and other
              form field values — to the extension via Chrome&rsquo;s native
              messaging API. The extension opens the target calendar site in a
              new tab and autofills the form. The operator solves any captcha
              and submits the form manually.
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              Data sharing
            </p>
            <p className="text-sm leading-relaxed">
              No data is shared with third parties. The only outbound data flow
              is form field values entered into the target calendar site&rsquo;s
              submission form — the same data an operator would type by hand.
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              Permissions
            </p>
            <p className="text-sm leading-relaxed">
              The extension requests <code>scripting</code>, <code>tabs</code>,
              and <code>storage</code> permissions solely to open and autofill
              tabs on the three calendar sites listed in its manifest. It is
              dormant on all other sites during normal browsing.
            </p>
          </div>
        </div>
      </section>

      <div className="rule-thick mb-8" aria-hidden="true" />

      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          Contact
        </h2>
        <p className="leading-relaxed">
          Questions about this policy:{' '}
          <a href="mailto:aryav@unc.edu" className="underline">
            aryav@unc.edu
          </a>
        </p>
      </section>

      <div className="border-t-2 border-[var(--color-border)] pt-4 text-center">
        <p className="text-xs italic text-[var(--color-text-muted)]">
          The Commons &bull; Est. 2026 &bull; Chapel Hill Area, N.C.
        </p>
      </div>
    </main>
  );
}
