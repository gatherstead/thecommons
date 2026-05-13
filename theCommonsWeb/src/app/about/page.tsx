import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'About — The Commons',
  description:
    'Learn about The Commons, a local community events aggregator for small NC towns.',
};

export default function AboutPage() {
  return (
    <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
      {/* Back link */}
      <nav className="mb-6">
        <Link
          href="/"
          className="text-xs uppercase tracking-wider no-underline hover:text-[var(--color-accent)] transition-colors"
        >
          &larr; Back to Feed
        </Link>
      </nav>

      {/* Page title */}
      <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
        <h1
          className="font-black tracking-tight leading-none mb-2"
          style={{
            fontSize: 'clamp(2.25rem, 6vw, 3.5rem)',
            fontFamily: 'var(--font-headline)',
          }}
        >
          About The Commons
        </h1>
        <p className="text-sm italic text-[var(--color-text-muted)]">
          Your Town&rsquo;s Digital Gathering Place
        </p>
      </header>

      {/* ── What is The Commons? ───────────────────────────────────── */}
      <section id="what" className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          What is The Commons?
        </h2>
        <p className="drop-cap leading-relaxed mb-4">
          The Commons is a community events aggregator built for small towns in
          North Carolina. Think of it as your neighborhood bulletin board &mdash;
          digitized, searchable, and always up to date. We gather happenings from
          local venues, community organizations, and individual neighbors into one
          place so you never miss what&rsquo;s going on around the corner.
        </p>
        <p className="leading-relaxed">
          Whether it&rsquo;s a farmers market in Carrboro, a book club in Chapel
          Hill, or a nature walk along the Haw River, The Commons makes it easy to
          find things to do without scrolling through five different Facebook
          groups, three newsletters, and a corkboard at the coffee shop.
        </p>
      </section>

      {/* ── Thick rule ─────────────────────────────────────────────── */}
      <div className="rule-thick mb-8" aria-hidden="true" />

      {/* ── Our Mission ────────────────────────────────────────────── */}
      <section id="mission" className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          Our Mission
        </h2>
        <p className="drop-cap leading-relaxed mb-4">
          We believe the best things in life happen locally. Our mission is
          simple: help people find reasons to stay in their town, meet their
          neighbors, and support the places that make their community worth living
          in.
        </p>
        <p className="leading-relaxed mb-4">
          Small towns don&rsquo;t lack for things to do &mdash; they lack for ways
          to hear about them. The Commons exists to close that gap. No algorithms
          deciding what you see, no pay-to-play promotion. Just a clean,
          chronological list of what&rsquo;s happening nearby.
        </p>
        <p className="leading-relaxed">
          We&rsquo;re not a ticketing platform. We&rsquo;re not a social network.
          We&rsquo;re a public service for community life &mdash; a commons, in
          the oldest sense of the word.
        </p>
      </section>

      {/* ── Thick rule ─────────────────────────────────────────────── */}
      <div className="rule-thick mb-8" aria-hidden="true" />

      {/* ── How It Works ───────────────────────────────────────────── */}
      <section id="how-it-works" className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          How It Works
        </h2>
        <p className="drop-cap leading-relaxed mb-4">
          Events arrive on The Commons through two channels: automated aggregation
          and community submissions.
        </p>
        <div className="border-l-2 border-[var(--color-border)] pl-4 mb-4 space-y-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              Aggregation
            </p>
            <p className="text-sm leading-relaxed">
              We periodically scan local event sources &mdash; venue calendars,
              community organizations, town newsletters &mdash; and pull in new
              listings automatically. Each event is reviewed before it appears on
              the feed.
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-black text-[var(--color-text-muted)] mb-0.5">
              Community Submissions
            </p>
            <p className="text-sm leading-relaxed">
              Anyone can submit an event directly through The Commons. Create an
              account, fill out the details, and your event joins the feed once
              it&rsquo;s approved. No cost, no catch.
            </p>
          </div>
        </div>
        <p className="leading-relaxed">
          All events are tagged, dated, and organized by town so you can filter
          down to exactly what interests you. See something wrong? Let us know
          &mdash; corrections are always welcome.
        </p>
      </section>

      {/* ── Thick rule ─────────────────────────────────────────────── */}
      <div className="rule-thick mb-8" aria-hidden="true" />

      {/* ── FAQ ────────────────────────────────────────────────────── */}
      <section id="faq" className="mb-8">
        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
          Frequently Asked Questions
        </h2>

        {/* ⚠️ PLACEHOLDER: Replace this FAQ content with real answers */}

        <div className="space-y-5">
          <div>
            <p className="font-bold mb-1">Is The Commons free to use?</p>
            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
              Yes. Browsing events and submitting your own listings is completely
              free. We have no plans to charge individuals or community
              organizations.
            </p>
          </div>

          <div className="border-t border-[var(--color-border-light)] pt-4">
            <p className="font-bold mb-1">
              How do I submit an event?
            </p>
            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
              Click &ldquo;Post an Event&rdquo; from the main feed. You&rsquo;ll
              need a free account. Fill in the details and your event will appear
              once reviewed.
            </p>
          </div>

          <div className="border-t border-[var(--color-border-light)] pt-4">
            <p className="font-bold mb-1">
              What towns do you cover?
            </p>
            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
              We currently cover Chapel Hill, Carrboro, and surrounding
              communities in the Triangle area of North Carolina. We&rsquo;re
              expanding to more towns soon.
            </p>
          </div>

          <div className="border-t border-[var(--color-border-light)] pt-4">
            <p className="font-bold mb-1">
              I found an error in a listing. How do I report it?
            </p>
            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
              Use the &ldquo;Submit a Correction&rdquo; link in the footer or
              contact us directly. We appreciate the help keeping things accurate.
            </p>
          </div>

          <div className="border-t border-[var(--color-border-light)] pt-4">
            <p className="font-bold mb-1">
              Can businesses or venues partner with The Commons?
            </p>
            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
              Absolutely. If you&rsquo;re a local venue or business, create a
              business account to post events directly. For broader partnerships,
              reach out to us.
            </p>
          </div>
        </div>
      </section>

      {/* ── Closing rule ───────────────────────────────────────────── */}
      <div className="border-t-2 border-[var(--color-border)] pt-4 text-center">
        <p className="text-xs italic text-[var(--color-text-muted)]">
          The Commons &bull; Est. 2026 &bull; Chapel Hill Area, N.C.
        </p>
      </div>
    </main>
  );
}
