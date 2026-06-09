'use client';

import { useEffect, useState, useCallback, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../hooks/useAuth';
import { getProfile, updateProfile, type UserProfileData, type EmailPreference } from '../../services/profileService';
import { getTowns } from '../../services/eventService';
import { Button } from '../../components/ui/Button';
import { SecuritySection } from '../../components/auth/SecuritySection';
import { FILTER_TAGS } from '../../constants/tags';
import type { TownOption } from '../../models/eventsModels';

type DigestFrequency = Exclude<EmailPreference, 'NEVER'>;

const FREQUENCY_OPTIONS: { value: DigestFrequency; label: string; description: string }[] = [
    { value: 'WEEKLY', label: 'Weekly', description: 'Every Monday morning' },
    { value: 'MONTHLY', label: 'Monthly', description: 'First of each month' },
];

function eqSets(a: Set<string>, b: Set<string>): boolean {
    if (a.size !== b.size) return false;
    for (const v of a) if (!b.has(v)) return false;
    return true;
}

export default function ProfilePage() {
    const { user, token, isAuthenticated, isInitializing, logout } = useAuth();
    const router = useRouter();

    const [profile, setProfile] = useState<UserProfileData | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [savedBanner, setSavedBanner] = useState(false);

    const [selectedFreq, setSelectedFreq] = useState<EmailPreference>('NEVER');
    const [lastFreq, setLastFreq] = useState<DigestFrequency>('WEEKLY');
    const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
    const [selectedCity, setSelectedCity] = useState('');
    const [towns, setTowns] = useState<TownOption[]>([]);

    const [showTownSave, setShowTownSave] = useState(false);
    const [showDigestSave, setShowDigestSave] = useState(false);
    const [showTagsSave, setShowTagsSave] = useState(false);

    const digestOn = selectedFreq !== 'NEVER';

    function setDigestOn(on: boolean) {
        if (on) {
            setSelectedFreq(lastFreq);
        } else {
            setSelectedFreq('NEVER');
        }
    }

    function setFrequency(freq: DigestFrequency) {
        setLastFreq(freq);
        setSelectedFreq(freq);
    }

    const isBusinessOrVenue = user?.user_type === 'BUSINESS' || user?.user_type === 'VENUE';

    const load = useCallback(async () => {
        if (!token) return;
        setIsLoading(true);
        setError(null);
        try {
            const data = await getProfile(token);
            setProfile(data);
            setSelectedFreq(data.email_preference);
            if (data.email_preference !== 'NEVER') setLastFreq(data.email_preference);
            setSelectedTags(new Set(data.tags));
            setSelectedCity(data.primary_city);
        } catch {
            setError('Could not load your profile.');
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => { getTowns().then(setTowns); }, []);

    const isDirty =
        profile !== null &&
        (selectedFreq !== profile.email_preference ||
            selectedCity !== profile.primary_city ||
            !eqSets(selectedTags, new Set(profile.tags)));

    const townDirty = profile !== null && selectedCity !== profile.primary_city;
    const digestDirty = profile !== null && selectedFreq !== profile.email_preference;
    const tagsDirty = profile !== null && !eqSets(selectedTags, new Set(profile.tags));

    async function save() {
        if (!token) return;
        setIsSaving(true);
        setError(null);
        try {
            const updated = await updateProfile(token, {
                email_preference: selectedFreq,
                tags: [...selectedTags],
                primary_city: selectedCity,
            });
            setProfile(updated);
            setSelectedFreq(updated.email_preference);
            if (updated.email_preference !== 'NEVER') setLastFreq(updated.email_preference);
            setSelectedTags(new Set(updated.tags));
            setSelectedCity(updated.primary_city);
            setSavedBanner(true);
            setTimeout(() => setSavedBanner(false), 3000);
        } catch {
            setError('Failed to save changes. Please try again.');
        } finally {
            setIsSaving(false);
        }
    }

    function toggleTag(tagId: string) {
        setSelectedTags(prev => {
            const next = new Set(prev);
            next.has(tagId) ? next.delete(tagId) : next.add(tagId);
            return next;
        });
    }

    function handleTownChange(slug: string) {
        setSelectedCity(slug);
        setShowTownSave(true);
    }

    function handleDigestToggle(on: boolean) {
        setDigestOn(on);
        setShowDigestSave(true);
    }

    function handleDigestFrequency(freq: DigestFrequency) {
        setFrequency(freq);
        setShowDigestSave(true);
    }

    function handleTagToggle(tagId: string) {
        toggleTag(tagId);
        setShowTagsSave(true);
    }

    if (isInitializing) {
        return (
            <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
                <div className="skeleton-block h-8 w-48 mb-4" />
                <div className="skeleton-block h-4 w-full mb-2" />
                <div className="skeleton-block h-4 w-3/4" />
            </main>
        );
    }

    if (!isAuthenticated) {
        return (
            <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
                <div className="border-2 border-[var(--color-border)] p-6 text-center">
                    <p className="font-bold mb-2">Sign in required</p>
                    <p className="text-sm text-[var(--color-text-muted)] mb-4">
                        You must be signed in to view your profile.
                    </p>
                    <Link href="/" className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors">
                        &larr; Return to Feed
                    </Link>
                </div>
            </main>
        );
    }

    // ── BUSINESS / VENUE profile ─────────────────────────────────────────────
    if (isBusinessOrVenue) {
        return (
            <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">

                <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                    <h1
                        className="font-black tracking-tight leading-none mb-1"
                        style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                    >
                        My Profile
                    </h1>
                    {profile && (
                        <p className="text-sm italic text-[var(--color-text-muted)]">{profile.email}</p>
                    )}
                </header>

                {error && (
                    <p className="text-sm text-[var(--color-accent)] mb-6 border border-[var(--color-accent)] px-3 py-2">
                        {error}
                    </p>
                )}
                {savedBanner && (
                    <p className="text-sm mb-6 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                        Profile saved.
                    </p>
                )}

                {/* Read-only identity */}
                <section className="mb-8">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                        Account
                    </h2>
                    <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
                        <div>
                            <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                                {user?.user_type === 'VENUE' ? 'Venue Name' : 'Business Name'}
                            </span>
                            <p className="font-bold">{profile?.business_name || user?.business_name || '—'}</p>
                        </div>
                        <div>
                            <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">Email</span>
                            <p className="font-bold">{user?.email}</p>
                        </div>
                    </div>
                </section>

                <div className="rule-thick mb-8" aria-hidden="true" />

                {isLoading ? (
                    <div className="space-y-3">
                        {[1, 2, 3].map(i => <div key={i} className="skeleton-block h-12 w-full" />)}
                    </div>
                ) : profile ? (
                    <>
                        <DigestSection
                            digestOn={digestOn}
                            selectedFreq={selectedFreq}
                            onToggle={setDigestOn}
                            onFrequencyChange={setFrequency}
                        />

                        <div className="rule-thick mb-8" aria-hidden="true" />

                        {/* ── Save ────────────────────────────────────────── */}
                        <div className="flex items-center gap-4 mb-10">
                            <Button variant="primary" onClick={save} disabled={!isDirty || isSaving}>
                                {isSaving ? 'Saving…' : 'Save Profile'}
                            </Button>
                            {isDirty && !isSaving && (
                                <span className="text-xs text-[var(--color-text-muted)] italic">Unsaved changes</span>
                            )}
                        </div>

                        <SecuritySection />

                        <div className="rule-thick mb-6" aria-hidden="true" />

                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={async () => { await logout(); router.push('/'); }}
                        >
                            Sign Out
                        </Button>
                    </>
                ) : null}
            </main>
        );
    }

    // ── LOCAL profile ────────────────────────────────────────────────────────
    return (
        <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">

            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-1"
                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                >
                    My Profile
                </h1>
                {profile && (
                    <p className="text-sm italic text-[var(--color-text-muted)]">
                        {profile.email}
                    </p>
                )}
            </header>

            {error && (
                <p className="text-sm text-[var(--color-accent)] mb-6 border border-[var(--color-accent)] px-3 py-2">
                    {error}
                </p>
            )}

            {savedBanner && (
                <p className="text-sm mb-6 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                    Preferences saved.
                </p>
            )}

            {isLoading ? (
                <div className="space-y-3">
                    {[1, 2, 3].map(i => <div key={i} className="skeleton-block h-12 w-full" />)}
                </div>
            ) : profile ? (
                <>
                    {/* ── My town ───────────────────────────────────────────── */}
                    <section className="mb-10">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                            My Town
                        </h2>
                        <p className="text-sm text-[var(--color-text-muted)] mb-4">
                            Choose your town so your weekly digest covers events near you.
                        </p>
                        <select
                            value={selectedCity}
                            onChange={e => handleTownChange(e.target.value)}
                            className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full max-w-xs"
                        >
                            <option value="">Select a town</option>
                            {towns.map(t => (
                                <option key={t.slug} value={t.slug}>{t.name}</option>
                            ))}
                        </select>
                        {showTownSave && (
                            <div className="mt-4">
                                <Button variant="primary" size="sm" onClick={save} disabled={!townDirty || isSaving}>
                                    {isSaving ? 'Saving…' : 'Save Changes'}
                                </Button>
                            </div>
                        )}
                    </section>

                    <div className="rule-thick mb-8" aria-hidden="true" />

                    <DigestSection
                        digestOn={digestOn}
                        selectedFreq={selectedFreq}
                        onToggle={handleDigestToggle}
                        onFrequencyChange={handleDigestFrequency}
                        footer={
                            <>
                                {digestOn && (
                                    <p className="text-xs text-[var(--color-text-muted)] mt-3 border-l-2 border-[var(--color-border-light)] pl-3">
                                        Digest emails include events matching your selected interests below.
                                        If no interests are selected, you&rsquo;ll receive all upcoming events.
                                    </p>
                                )}
                                {showDigestSave && (
                                    <div className="mt-4">
                                        <Button variant="primary" size="sm" onClick={save} disabled={!digestDirty || isSaving}>
                                            {isSaving ? 'Saving…' : 'Save Changes'}
                                        </Button>
                                    </div>
                                )}
                            </>
                        }
                    />

                    <div className="rule-thick mb-8" aria-hidden="true" />

                    {/* ── Tag interests ─────────────────────────────────────── */}
                    <section className="mb-10">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                            My Interests
                        </h2>
                        <p className="text-sm text-[var(--color-text-muted)] mb-4">
                            Select the types of events you care about. Your digest will be filtered to match.
                        </p>
                        <div className="flex flex-wrap gap-2">
                            {FILTER_TAGS.map(tag => {
                                const active = selectedTags.has(tag.id);
                                return (
                                    <button
                                        key={tag.id}
                                        type="button"
                                        onClick={() => handleTagToggle(tag.id)}
                                        aria-pressed={active}
                                        className={`text-xs uppercase tracking-wider px-3 py-1.5 border transition-colors cursor-pointer ${
                                            active
                                                ? 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]'
                                                : 'bg-transparent border-[var(--color-border)] hover:bg-[var(--color-bg-alt)]'
                                        }`}
                                    >
                                        {tag.label}
                                    </button>
                                );
                            })}
                        </div>
                        {selectedTags.size === 0 && (
                            <p className="text-xs text-[var(--color-text-muted)] mt-3 italic">
                                No interests selected — your digest will include all upcoming events.
                            </p>
                        )}
                        {showTagsSave && (
                            <div className="mt-4">
                                <Button variant="primary" size="sm" onClick={save} disabled={!tagsDirty || isSaving}>
                                    {isSaving ? 'Saving…' : 'Save Changes'}
                                </Button>
                            </div>
                        )}
                    </section>

                    <div className="rule-thick mb-8" aria-hidden="true" />

                    {/* ── Follow creators — coming soon ─────────────────────── */}
                    <section className="mb-10">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-3">
                            Follow Creators — Coming Soon
                        </h2>
                        <div className="border-l-2 border-[var(--color-border)] pl-4">
                            <p className="text-sm text-[var(--color-text-muted)]">
                                Soon you&rsquo;ll be able to follow specific local businesses and venues
                                and get their events delivered directly to your inbox.
                            </p>
                        </div>
                    </section>

                    <SecuritySection />

                    <div className="rule-thick mb-6" aria-hidden="true" />

                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={async () => { await logout(); router.push('/'); }}
                    >
                        Sign Out
                    </Button>
                </>
            ) : null}
        </main>
    );
}

function ToggleSwitch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
    return (
        <label className="inline-flex items-center gap-3 cursor-pointer group">
            <input
                type="checkbox"
                role="switch"
                aria-checked={checked}
                checked={checked}
                onChange={e => onChange(e.target.checked)}
                className="sr-only"
            />
            <span
                className={`relative inline-block w-10 h-5 border-2 transition-colors duration-150 shrink-0 ${
                    checked
                        ? 'bg-[var(--color-text)] border-[var(--color-text)]'
                        : 'bg-transparent border-[var(--color-border)]'
                }`}
            >
                <span
                    className={`absolute top-0.5 w-3 h-3 transition-all duration-150 ${
                        checked
                            ? 'right-0.5 bg-[var(--color-bg)]'
                            : 'left-0.5 bg-[var(--color-text-muted)]'
                    }`}
                />
            </span>
            <span className="text-xs uppercase tracking-wider font-bold group-hover:text-[var(--color-accent)] transition-colors">
                {checked ? 'On' : 'Off'}
            </span>
        </label>
    );
}

function DigestSection({
    digestOn,
    selectedFreq,
    onToggle,
    onFrequencyChange,
    footer,
}: {
    digestOn: boolean;
    selectedFreq: EmailPreference;
    onToggle: (on: boolean) => void;
    onFrequencyChange: (freq: DigestFrequency) => void;
    footer?: ReactNode;
}) {
    return (
        <section id="digest" className="mb-10 scroll-mt-24">
            <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                Digest
            </h2>

            <div className="mb-5">
                <span className="block text-sm font-bold mb-0.5">Receive Digest</span>
                <span className="block text-xs text-[var(--color-text-muted)] mb-3">
                    Email me a curated list of upcoming local events.
                </span>
                <ToggleSwitch checked={digestOn} onChange={onToggle} />
            </div>

            <fieldset
                disabled={!digestOn}
                aria-disabled={!digestOn}
                className={`space-y-2 transition-opacity ${digestOn ? 'opacity-100' : 'opacity-50'}`}
            >
                <legend className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                    Frequency
                </legend>
                {FREQUENCY_OPTIONS.map(opt => (
                    <label
                        key={opt.value}
                        className={`flex items-start gap-3 group ${digestOn ? 'cursor-pointer' : 'cursor-not-allowed'}`}
                    >
                        <input
                            type="radio"
                            name="frequency"
                            value={opt.value}
                            checked={selectedFreq === opt.value}
                            onChange={() => onFrequencyChange(opt.value)}
                            className="mt-1 accent-[var(--color-accent)] shrink-0"
                        />
                        <span>
                            <span className={`text-sm font-bold transition-colors ${digestOn ? 'group-hover:text-[var(--color-accent)]' : ''}`}>
                                {opt.label}
                            </span>
                            <span className="text-xs text-[var(--color-text-muted)] ml-2">
                                {opt.description}
                            </span>
                        </span>
                    </label>
                ))}
            </fieldset>

            {footer}
        </section>
    );
}
