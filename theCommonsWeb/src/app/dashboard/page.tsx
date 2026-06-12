'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../hooks/useAuth';
import { useTowns } from '../../hooks/useTowns';
import { getMyEvents, deleteStagedEvent, deletePublishedEvent } from '../../services/eventService';
import { getProfile, updateProfile, type UserProfileData } from '../../services/profileService';
import { getMyBusiness, createBusiness, updateBusiness, deleteBusiness } from '../../services/businessService';
import { EditEventModal } from '../../components/events/EditEventModal';
import { Button } from '../../components/ui/Button';
import { FILTER_TAGS } from '../../constants/tags';
import type { MyEventSummary } from '../../models/eventsModels';
import type { BusinessProfile } from '../../models/businessModels';

const STATUS_LABELS: Record<string, string> = {
    pending: 'Under Review',
    approved: 'Approved',
    rejected: 'Rejected',
    duplicate: 'Duplicate',
    published: 'Published',
};

const STATUS_STYLES: Record<string, string> = {
    pending: 'border-[var(--color-border-light)] text-[var(--color-text-muted)]',
    approved: 'border-[var(--color-border)] text-[var(--color-text)]',
    rejected: 'border-[var(--color-accent)] text-[var(--color-accent)]',
    duplicate: 'border-[var(--color-border-light)] text-[var(--color-text-muted)]',
    published: 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]',
};

function formatDate(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
    });
}

function eqSets(a: Set<string>, b: Set<string>): boolean {
    if (a.size !== b.size) return false;
    for (const v of a) if (!b.has(v)) return false;
    return true;
}

export default function DashboardPage() {
    const { user, token, isAuthenticated, isInitializing, logout } = useAuth();
    const router = useRouter();
    const queryClient = useQueryClient();

    // Events
    const [editingEventId, setEditingEventId] = useState<string | null>(null);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    // Profile settings
    const [profile, setProfile] = useState<UserProfileData | null>(null);
    const [isLoadingProfile, setIsLoadingProfile] = useState(false);
    const [settingsError, setSettingsError] = useState<string | null>(null);
    const [savedBanner, setSavedBanner] = useState(false);
    const [selectedCity, setSelectedCity] = useState('');
    const [address, setAddress] = useState('');
    const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
    const [selectedUserType, setSelectedUserType] = useState<'BUSINESS' | 'VENUE'>('BUSINESS');

    // Business listing
    const [businessError, setBusinessError] = useState<string | null>(null);
    const [businessSaved, setBusinessSaved] = useState(false);
    const [bizName, setBizName] = useState('');
    const [bizDescription, setBizDescription] = useState('');
    const [bizTags, setBizTags] = useState<Set<string>>(new Set());
    const [bizServiceArea, setBizServiceArea] = useState<Set<string>>(new Set());
    const [bizContactEmail, setBizContactEmail] = useState('');
    const [bizContactPhone, setBizContactPhone] = useState('');
    const [bizPublished, setBizPublished] = useState(false);

    const isBusiness = user?.user_type === 'BUSINESS' || user?.user_type === 'VENUE';
    const isBusinessOnly = user?.user_type === 'BUSINESS';
    // Use selectedUserType (reflects any unsaved change) for venue-specific UI
    const displayIsVenue = selectedUserType === 'VENUE';

    const myEventsQuery = useQuery({
        queryKey: ['my-events', token],
        queryFn: () => getMyEvents(token!),
        enabled: !!token && isBusiness,
    });
    const myEvents = myEventsQuery.data ?? [];
    const isLoadingEvents = myEventsQuery.isLoading;
    const fetchError = myEventsQuery.isError ? 'Could not load your listings.' : null;

    const townsQuery = useTowns();
    const towns = townsQuery.data ?? [];

    const loadProfile = useCallback(async () => {
        if (!token) return;
        setIsLoadingProfile(true);
        try {
            const data = await getProfile(token);
            setProfile(data);
            setSelectedCity(data.primary_city || '');
            setAddress(data.address || '');
            setSelectedTags(new Set(data.tags));
            setSelectedUserType((data.user_type as 'BUSINESS' | 'VENUE') ?? 'BUSINESS');
        } catch {
            setSettingsError('Could not load account settings.');
        } finally {
            setIsLoadingProfile(false);
        }
    }, [token]);

    const populateBusinessForm = useCallback((data: BusinessProfile) => {
        setBizName(data.business_name);
        setBizDescription(data.description || '');
        setBizTags(new Set(data.tag_names));
        setBizServiceArea(new Set(data.service_area));
        setBizContactEmail(data.contact_email || '');
        setBizContactPhone(data.contact_phone || '');
        setBizPublished(data.is_published);
    }, []);

    const businessQuery = useQuery({
        queryKey: ['business', 'me', token],
        queryFn: () => getMyBusiness(token!),
        enabled: !!token && isBusinessOnly,
    });
    // null is valid data: "no listing yet". undefined means not loaded.
    const business = businessQuery.data ?? null;
    const isLoadingBusiness = businessQuery.isLoading;
    const businessLoadError = businessQuery.isError ? 'Could not load your business listing.' : null;

    // Seed the business form draft once per token, not on every refetch, so a
    // background refetch can't wipe unsaved edits.
    const hasSeededBiz = useRef(false);
    useEffect(() => { hasSeededBiz.current = false; }, [token]);
    useEffect(() => {
        if (hasSeededBiz.current || !businessQuery.data) return;
        hasSeededBiz.current = true;
        populateBusinessForm(businessQuery.data);
    }, [businessQuery.data, populateBusinessForm]);

    useEffect(() => { if (isBusiness) loadProfile(); }, [loadProfile, isBusiness]);

    const isSettingsDirty =
        profile !== null &&
        (selectedCity !== (profile.primary_city || '') ||
            address !== (profile.address || '') ||
            !eqSets(selectedTags, new Set(profile.tags)) ||
            selectedUserType !== profile.user_type);

    const settingsMutation = useMutation({
        mutationFn: (payload: Parameters<typeof updateProfile>[1]) => updateProfile(token!, payload),
        onSuccess: updated => {
            setProfile(updated);
            setSelectedCity(updated.primary_city || '');
            setAddress(updated.address || '');
            setSelectedTags(new Set(updated.tags));
            setSelectedUserType((updated.user_type as 'BUSINESS' | 'VENUE') ?? 'BUSINESS');
            setSavedBanner(true);
            setTimeout(() => setSavedBanner(false), 3000);
            // Refreshes useAuth().user (header name, user_type gates).
            queryClient.invalidateQueries({ queryKey: ['profile'] });
        },
        onError: () => setSettingsError('Failed to save settings. Please try again.'),
    });
    const isSaving = settingsMutation.isPending;

    function saveSettings() {
        if (!token || !isSettingsDirty) return;
        setSettingsError(null);
        settingsMutation.mutate({
            primary_city: selectedCity,
            address,
            tags: [...selectedTags],
            user_type: selectedUserType,
        });
    }

    function toggleTag(tagId: string) {
        setSelectedTags(prev => {
            const next = new Set(prev);
            next.has(tagId) ? next.delete(tagId) : next.add(tagId);
            return next;
        });
    }

    function toggleInSet(setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) {
        setter(prev => {
            const next = new Set(prev);
            next.has(value) ? next.delete(value) : next.add(value);
            return next;
        });
    }

    const isBusinessDirty =
        business === null
            ? bizName.trim().length > 0
            : bizName !== business.business_name ||
              bizDescription !== (business.description || '') ||
              !eqSets(bizTags, new Set(business.tag_names)) ||
              !eqSets(bizServiceArea, new Set(business.service_area)) ||
              bizContactEmail !== (business.contact_email || '') ||
              bizContactPhone !== (business.contact_phone || '') ||
              bizPublished !== business.is_published;

    const saveBusinessMutation = useMutation({
        mutationFn: (payload: Parameters<typeof createBusiness>[1]) =>
            business === null
                ? createBusiness(token!, payload)
                : updateBusiness(token!, business.uuid, payload),
        onSuccess: saved => {
            // setQueryData instead of invalidate: avoids a refetch racing the form re-seed.
            queryClient.setQueryData<BusinessProfile | null>(['business', 'me', token], saved);
            populateBusinessForm(saved);
            setBusinessSaved(true);
            setTimeout(() => setBusinessSaved(false), 3000);
        },
        onError: () => setBusinessError('Failed to save your listing. Please try again.'),
    });
    const isSavingBusiness = saveBusinessMutation.isPending;

    function saveBusiness() {
        if (!token || !isBusinessDirty || !bizName.trim()) return;
        setBusinessError(null);
        saveBusinessMutation.mutate({
            business_name: bizName.trim(),
            description: bizDescription,
            tags: [...bizTags],
            service_area: [...bizServiceArea],
            contact_email: bizContactEmail,
            contact_phone: bizContactPhone,
            is_published: bizPublished,
        });
    }

    const deleteBusinessMutation = useMutation({
        mutationFn: (uuid: string) => deleteBusiness(token!, uuid),
        onSuccess: () => {
            queryClient.setQueryData<BusinessProfile | null>(['business', 'me', token], null);
            setBizName('');
            setBizDescription('');
            setBizTags(new Set());
            setBizServiceArea(new Set());
            setBizContactEmail('');
            setBizContactPhone('');
            setBizPublished(false);
        },
        onError: () => setBusinessError('Could not delete your listing. Please try again.'),
    });
    const isDeletingBusiness = deleteBusinessMutation.isPending;

    function handleDeleteBusiness() {
        if (!token || !business) return;
        if (!window.confirm('Delete your business listing? This cannot be undone.')) return;
        setBusinessError(null);
        deleteBusinessMutation.mutate(business.uuid);
    }

    const deleteEventMutation = useMutation({
        mutationFn: (event: MyEventSummary) =>
            event.status === 'published'
                ? deletePublishedEvent(token!, event.id)
                : deleteStagedEvent(token!, event.id),
        onSuccess: (_data, event) => {
            // Instant removal, then invalidate so the list reconciles with the server.
            queryClient.setQueryData<MyEventSummary[]>(
                ['my-events', token],
                old => old?.filter(e => e.id !== event.id),
            );
            queryClient.invalidateQueries({ queryKey: ['my-events'] });
            queryClient.invalidateQueries({ queryKey: ['events'] });
        },
        onError: (_err, event) => setDeleteError(`Could not delete "${event.title}". Please try again.`),
    });
    const deletingEventId = deleteEventMutation.isPending
        ? deleteEventMutation.variables?.id ?? null
        : null;

    function handleDelete(event: MyEventSummary) {
        if (!token) return;
        setDeleteError(null);
        deleteEventMutation.mutate(event);
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
                        You must be signed in to access the dashboard.
                    </p>
                    <Link href="/" className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors">
                        &larr; Return to Feed
                    </Link>
                </div>
            </main>
        );
    }

    if (!isBusiness) {
        return (
            <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">
                <div className="border-2 border-[var(--color-border)] p-6 text-center">
                    <p className="font-bold mb-2">Business &amp; venue accounts only</p>
                    <p className="text-sm text-[var(--color-text-muted)] mb-4">
                        The dashboard is available to business and venue accounts. Your account type is{' '}
                        <span className="font-bold">{user?.user_type}</span>.
                    </p>
                    <Link href="/" className="text-xs uppercase tracking-wider font-bold hover:text-[var(--color-accent)] transition-colors">
                        &larr; Return to Feed
                    </Link>
                </div>
            </main>
        );
    }

    return (
        <>
            <main id="main-content" className="max-w-[720px] mx-auto px-4 py-8">

                <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <h1
                                className="font-black tracking-tight leading-none mb-1"
                                style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                            >
                                {displayIsVenue ? 'Venue Dashboard' : 'Business Dashboard'}
                            </h1>
                            <p className="text-sm italic text-[var(--color-text-muted)]">
                                {user?.business_name || user?.email}
                            </p>
                        </div>
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={async () => { await logout(); router.push('/'); }}
                        >
                            Sign Out
                        </Button>
                    </div>
                </header>

                {/* ── My Listings ────────────────────────────────────────── */}
                <section className="mb-10">
                    <div className="flex items-baseline justify-between mb-3">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 flex-1 mr-4">
                            My Listings
                        </h2>
                        <Button variant="primary" size="sm" onClick={() => router.push('/post')}>
                            + Post New Event
                        </Button>
                    </div>

                    {fetchError && (
                        <p className="text-sm text-[var(--color-accent)] mb-4">{fetchError}</p>
                    )}
                    {deleteError && (
                        <p className="text-sm text-[var(--color-accent)] mb-4 border border-[var(--color-accent)] px-3 py-2">
                            {deleteError}
                        </p>
                    )}

                    {isLoadingEvents ? (
                        <div className="space-y-2">
                            {[1, 2, 3].map(i => <div key={i} className="skeleton-block h-12 w-full" />)}
                        </div>
                    ) : myEvents.length === 0 ? (
                        <div className="border border-[var(--color-border-light)] p-6 text-center">
                            <p className="text-sm text-[var(--color-text-muted)] mb-3">
                                No listings yet. Post your first event to get started.
                            </p>
                            <Button variant="secondary" size="sm" onClick={() => router.push('/post')}>
                                Post New Event
                            </Button>
                        </div>
                    ) : (
                        <div className="border-t border-[var(--color-border)]">
                            {myEvents.map((event, idx) => (
                                <div
                                    key={event.id}
                                    className={`grid grid-cols-[1fr_auto_auto_auto] gap-x-3 items-center py-3 ${
                                        idx < myEvents.length - 1 ? 'border-b border-[var(--color-border-light)]' : ''
                                    }`}
                                >
                                    <div className="min-w-0">
                                        <p className="font-bold truncate text-sm leading-tight">{event.title}</p>
                                        <p className="text-xs text-[var(--color-text-muted)] truncate">
                                            {event.venue} &middot; {formatDate(event.date)}
                                        </p>
                                    </div>
                                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 border whitespace-nowrap ${STATUS_STYLES[event.status] ?? ''}`}>
                                        {STATUS_LABELS[event.status] ?? event.status}
                                    </span>
                                    {event.status !== 'published' ? (
                                        <button
                                            type="button"
                                            onClick={() => setEditingEventId(event.id)}
                                            className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 border border-[var(--color-border)] hover:bg-[var(--color-bg-alt)] transition-colors whitespace-nowrap cursor-pointer"
                                        >
                                            Edit
                                        </button>
                                    ) : (
                                        <span className="w-[42px]" />
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => handleDelete(event)}
                                        disabled={deletingEventId === event.id}
                                        className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 border border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] transition-colors whitespace-nowrap cursor-pointer disabled:opacity-40"
                                    >
                                        {deletingEventId === event.id ? '…' : 'Delete'}
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </section>

                <div className="rule-thick mb-8" aria-hidden="true" />

                {/* ── Account Settings ───────────────────────────────────── */}
                <section className="mb-10">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-4">
                        Account Settings
                    </h2>

                    {settingsError && (
                        <p className="text-sm text-[var(--color-accent)] mb-4 border border-[var(--color-accent)] px-3 py-2">
                            {settingsError}
                        </p>
                    )}
                    {savedBanner && (
                        <p className="text-sm mb-4 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                            Settings saved.
                        </p>
                    )}

                    {isLoadingProfile ? (
                        <div className="space-y-3">
                            {[1, 2].map(i => <div key={i} className="skeleton-block h-10 w-full" />)}
                        </div>
                    ) : (
                        <>
                            {/* Account type */}
                            <div className="mb-6">
                                <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                    Account Type
                                </label>
                                <div className="flex gap-3">
                                    {(['BUSINESS', 'VENUE'] as const).map(type => (
                                        <label key={type} className="flex items-center gap-2 cursor-pointer group">
                                            <input
                                                type="radio"
                                                name="user_type"
                                                value={type}
                                                checked={selectedUserType === type}
                                                onChange={() => setSelectedUserType(type)}
                                                className="accent-[var(--color-accent)]"
                                            />
                                            <span className="text-sm font-bold group-hover:text-[var(--color-accent)] transition-colors capitalize">
                                                {type.charAt(0) + type.slice(1).toLowerCase()}
                                            </span>
                                        </label>
                                    ))}
                                </div>
                                <p className="text-xs text-[var(--color-text-muted)] mt-2 border-l-2 border-[var(--color-border-light)] pl-3">
                                    Venues host events at a physical location. Businesses promote services or sponsor events.
                                </p>
                            </div>

                            {/* Location */}
                            <div className="mb-6">
                                <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                    Primary Town
                                </label>
                                <select
                                    value={selectedCity}
                                    onChange={e => setSelectedCity(e.target.value)}
                                    className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full max-w-xs"
                                >
                                    <option value="">Select a town</option>
                                    {towns.map(t => (
                                        <option key={t.slug} value={t.slug}>{t.name}</option>
                                    ))}
                                </select>
                            </div>

                            {displayIsVenue && (
                                <div className="mb-6">
                                    <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                        Venue Address
                                    </label>
                                    <input
                                        type="text"
                                        value={address}
                                        onChange={e => setAddress(e.target.value)}
                                        placeholder="123 Main St, Chapel Hill, NC"
                                        className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full max-w-sm"
                                    />
                                </div>
                            )}

                            {/* Services & categories */}
                            <div className="mb-6">
                                <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                    Services &amp; Categories
                                </label>
                                <p className="text-xs text-[var(--color-text-muted)] mb-3">
                                    {displayIsVenue
                                        ? 'Tag the types of events you host. Used to surface relevant service requests.'
                                        : 'Tag the types of events you offer or sponsor. Used to match you with relevant opportunities.'}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    {FILTER_TAGS.map(tag => {
                                        const active = selectedTags.has(tag.id);
                                        return (
                                            <button
                                                key={tag.id}
                                                type="button"
                                                onClick={() => toggleTag(tag.id)}
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
                            </div>

                            <div className="flex items-center gap-4">
                                <Button
                                    variant="primary"
                                    onClick={saveSettings}
                                    disabled={!isSettingsDirty || isSaving}
                                >
                                    {isSaving ? 'Saving…' : 'Save Settings'}
                                </Button>
                                {isSettingsDirty && !isSaving && (
                                    <span className="text-xs text-[var(--color-text-muted)] italic">Unsaved changes</span>
                                )}
                            </div>
                        </>
                    )}
                </section>

                <div className="rule-thick mb-8" aria-hidden="true" />

                {/* ── Coming Soon — Auto-Posting ───────────────────────────── */}
                <section className="mb-8">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
                        Auto-Posting — Coming Soon
                    </h2>
                    <div className="border-l-2 border-[var(--color-border)] pl-4">
                        <p className="font-bold mb-1 text-sm">Cross-platform auto-posting &mdash; coming soon.</p>
                        <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
                            Soon you&rsquo;ll be able to connect your existing social accounts and have your
                            events automatically posted to The Commons, Facebook, Instagram, and more &mdash;
                            all from one place. No more copy-pasting across platforms.
                        </p>
                    </div>
                </section>

                {/* ── My Business Listing (business accounts only) ─────────── */}
                {isBusinessOnly && (
                    <section className="mb-8">
                        <div className="flex items-baseline justify-between mb-3">
                            <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 flex-1 mr-4">
                                My Business Listing
                            </h2>
                            {business && (
                                <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 border whitespace-nowrap ${
                                    business.is_published
                                        ? 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]'
                                        : 'border-[var(--color-border-light)] text-[var(--color-text-muted)]'
                                }`}>
                                    {business.is_published ? 'Published' : 'Draft'}
                                </span>
                            )}
                        </div>

                        {(businessError || businessLoadError) && (
                            <p className="text-sm text-[var(--color-accent)] mb-4 border border-[var(--color-accent)] px-3 py-2">
                                {businessError ?? businessLoadError}
                            </p>
                        )}
                        {businessSaved && (
                            <p className="text-sm mb-4 border border-[var(--color-border)] px-3 py-2 bg-[var(--color-bg-alt)]">
                                Listing saved.
                            </p>
                        )}

                        {isLoadingBusiness ? (
                            <div className="space-y-3">
                                {[1, 2].map(i => <div key={i} className="skeleton-block h-10 w-full" />)}
                            </div>
                        ) : (
                            <>
                                {!business && (
                                    <p className="text-sm text-[var(--color-text-muted)] mb-5 border-l-2 border-[var(--color-border-light)] pl-3">
                                        You don&rsquo;t have a listing yet. Fill out the form below and create one
                                        to appear in the local business directory.
                                    </p>
                                )}

                                {/* Business name */}
                                <div className="mb-6">
                                    <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                        Business Name
                                    </label>
                                    <input
                                        type="text"
                                        value={bizName}
                                        onChange={e => setBizName(e.target.value)}
                                        placeholder="e.g. Carrboro Catering Co."
                                        className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full max-w-sm"
                                    />
                                </div>

                                {/* Description */}
                                <div className="mb-6">
                                    <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                        Description
                                    </label>
                                    <textarea
                                        value={bizDescription}
                                        onChange={e => setBizDescription(e.target.value)}
                                        rows={4}
                                        placeholder="What does your business offer?"
                                        className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full"
                                    />
                                </div>

                                {/* Tags */}
                                <div className="mb-6">
                                    <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                        Tags
                                    </label>
                                    <div className="flex flex-wrap gap-2">
                                        {FILTER_TAGS.map(tag => {
                                            const active = bizTags.has(tag.id);
                                            return (
                                                <button
                                                    key={tag.id}
                                                    type="button"
                                                    onClick={() => toggleInSet(setBizTags, tag.id)}
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
                                </div>

                                {/* Service area */}
                                <div className="mb-6">
                                    <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                        Service Area
                                    </label>
                                    <p className="text-xs text-[var(--color-text-muted)] mb-3">
                                        Towns your business serves.
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {towns.map(town => {
                                            const active = bizServiceArea.has(town.slug);
                                            return (
                                                <button
                                                    key={town.slug}
                                                    type="button"
                                                    onClick={() => toggleInSet(setBizServiceArea, town.slug)}
                                                    aria-pressed={active}
                                                    className={`text-xs uppercase tracking-wider px-3 py-1.5 border transition-colors cursor-pointer ${
                                                        active
                                                            ? 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]'
                                                            : 'bg-transparent border-[var(--color-border)] hover:bg-[var(--color-bg-alt)]'
                                                    }`}
                                                >
                                                    {town.name}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Contact */}
                                <div className="mb-6 grid gap-4 sm:grid-cols-2 max-w-lg">
                                    <div>
                                        <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                            Contact Email
                                        </label>
                                        <input
                                            type="email"
                                            value={bizContactEmail}
                                            onChange={e => setBizContactEmail(e.target.value)}
                                            placeholder="hello@business.com"
                                            className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-wider font-bold mb-2">
                                            Contact Phone
                                        </label>
                                        <input
                                            type="tel"
                                            value={bizContactPhone}
                                            onChange={e => setBizContactPhone(e.target.value)}
                                            placeholder="(919) 555-0123"
                                            className="border border-[var(--color-border)] bg-[var(--color-bg)] text-sm px-3 py-2 w-full"
                                        />
                                    </div>
                                </div>

                                {/* Published toggle */}
                                <div className="mb-6">
                                    <label className="flex items-center gap-2 cursor-pointer group w-fit">
                                        <input
                                            type="checkbox"
                                            checked={bizPublished}
                                            onChange={e => setBizPublished(e.target.checked)}
                                            className="accent-[var(--color-accent)]"
                                        />
                                        <span className="text-sm font-bold group-hover:text-[var(--color-accent)] transition-colors">
                                            Published
                                        </span>
                                    </label>
                                    <p className="text-xs text-[var(--color-text-muted)] mt-2 border-l-2 border-[var(--color-border-light)] pl-3">
                                        When published, your listing is visible to venues browsing the directory.
                                    </p>
                                </div>

                                <div className="flex items-center gap-4">
                                    <Button
                                        variant="primary"
                                        onClick={saveBusiness}
                                        disabled={!isBusinessDirty || isSavingBusiness || !bizName.trim()}
                                    >
                                        {isSavingBusiness
                                            ? 'Saving…'
                                            : business === null ? 'Create Listing' : 'Save Listing'}
                                    </Button>
                                    {business && (
                                        <button
                                            type="button"
                                            onClick={handleDeleteBusiness}
                                            disabled={isDeletingBusiness}
                                            className="text-xs uppercase tracking-wider font-bold px-3 py-1.5 border border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] transition-colors cursor-pointer disabled:opacity-40"
                                        >
                                            {isDeletingBusiness ? 'Deleting…' : 'Delete Listing'}
                                        </button>
                                    )}
                                    {isBusinessDirty && !isSavingBusiness && (
                                        <span className="text-xs text-[var(--color-text-muted)] italic">Unsaved changes</span>
                                    )}
                                </div>
                            </>
                        )}
                    </section>
                )}

                {/* ── Coming Soon — Post a Request for Services (venue only) ── */}
                {displayIsVenue && (
                    <section className="mb-8">
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] mb-3 border-b border-[var(--color-border-light)] pb-1">
                            Post a Request for Services — Coming Soon
                        </h2>
                        <div className="border-l-2 border-[var(--color-border)] pl-4">
                            <p className="font-bold mb-1 text-sm">Find vendors &amp; performers &mdash; coming soon.</p>
                            <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">
                                Soon you&rsquo;ll be able to post open calls for musicians, caterers, photographers,
                                and other service providers directly through The Commons. Let the local talent come to you.
                            </p>
                        </div>
                    </section>
                )}
            </main>

            {editingEventId && token && (
                <EditEventModal
                    isOpen={!!editingEventId}
                    onClose={() => setEditingEventId(null)}
                    eventId={editingEventId}
                    token={token}
                    towns={towns}
                />
            )}
        </>
    );
}
