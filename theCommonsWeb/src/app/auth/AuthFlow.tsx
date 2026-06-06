'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '../../hooks/useAuth';
import { updateProfile, type EmailPreference } from '../../services/profileService';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { FILTER_TAGS } from '../../constants/tags';
import type { UserType } from '../../models/authModels';

type Step = 'type' | 'email' | 'prefs' | 'password';

const USER_TYPE_OPTIONS: { value: UserType; label: string; blurb: string }[] = [
    { value: 'LOCAL', label: 'Local', blurb: 'I live here and want to find things to do.' },
    { value: 'BUSINESS', label: 'Business', blurb: 'I offer services for events — catering, music, bar, and more.' },
    { value: 'VENUE', label: 'Venue', blurb: 'I have a space and host events.' },
];

export function AuthFlow({
    defaultSignIn,
    heading,
    subheading,
}: {
    defaultSignIn: boolean;
    heading?: string;
    subheading?: string;
}) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { enter, login, isAuthenticated, isInitializing } = useAuth();

    const intent = searchParams.get('intent');
    const headingParam = searchParams.get('heading') ?? undefined;
    const subheadingParam = searchParams.get('subheading') ?? undefined;
    const typeParam = searchParams.get('type')?.toUpperCase();
    const presetType: UserType | null =
        typeParam === 'LOCAL' || typeParam === 'BUSINESS' || typeParam === 'VENUE'
            ? typeParam
            : null;

    const explicitRedirect = searchParams.get('redirect');
    const redirectTo =
        explicitRedirect
            ?? (intent === 'digest' ? '/profile#digest' : '/');

    const [step, setStep] = useState<Step>(
        defaultSignIn ? 'email' : (presetType ? 'email' : 'type'),
    );
    const [userType, setUserType] = useState<UserType>(presetType ?? 'LOCAL');
    const [businessName, setBusinessName] = useState('');
    const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    const redirected = useRef(false);
    useEffect(() => {
        if (!isInitializing && isAuthenticated && !redirected.current) {
            redirected.current = true;
            router.replace(redirectTo);
        }
    }, [isAuthenticated, isInitializing, redirectTo, router]);

    const isBusinessOrVenue = userType === 'BUSINESS' || userType === 'VENUE';

    function toggleTag(id: string) {
        setSelectedTags(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    }

    async function applySignupPrefs() {
        try {
            const res = await fetch('/api/auth/token', { credentials: 'include' });
            if (!res.ok) return;
            const { token } = await res.json();
            if (!token) return;
            const patch: { tags: string[]; email_preference?: EmailPreference } = { tags: [...selectedTags] };
            if (intent === 'digest') patch.email_preference = 'WEEKLY';
            await updateProfile(token, patch);
        } catch {
            // Non-fatal: user is signed in, they can adjust prefs in profile.
        }
    }

    function goToLogin() {
        setError(null);
        const q = new URLSearchParams();
        if (redirectTo !== '/') q.set('redirect', redirectTo);
        if (intent) q.set('intent', intent);
        router.push(`/auth/login${q.size ? '?' + q : ''}`);
    }

    function goToSignup() {
        setError(null);
        const q = new URLSearchParams();
        if (redirectTo !== '/') q.set('redirect', redirectTo);
        if (intent) q.set('intent', intent);
        router.push(`/auth/signup${q.size ? '?' + q : ''}`);
    }

    async function submitEmail(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            const result = await enter({
                email: email.trim(),
                user_type: defaultSignIn ? undefined : userType,
                name: defaultSignIn ? undefined : businessName.trim(),
            });
            if (result.requiresPassword) {
                setStep('password');
                return;
            }
            // New signups get an optional preferences step; returning/passwordless
            // users (and the sign-in flow) go straight through.
            if (result.isNew && !defaultSignIn) {
                setStep('prefs');
                return;
            }
            router.replace(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Something went wrong.');
        } finally {
            setIsLoading(false);
        }
    }

    async function finishPrefs() {
        setIsLoading(true);
        await applySignupPrefs();
        router.replace(redirectTo);
    }

    async function submitPassword(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setIsLoading(true);
        try {
            await login({ email: email.trim(), password });
            router.replace(redirectTo);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Incorrect password.');
        } finally {
            setIsLoading(false);
        }
    }

    /* ── Google sign-in — temporarily disabled, revisit later ──────────────
       Google OAuth is commented out for now: the popup returned `invalid_code`
       and it bypassed the user-type selection. See /auth/google-popup.

    function handleGoogle() {
        setError(null);
        if (popupRef.current && !popupRef.current.closed) {
            popupRef.current.focus();
            return;
        }
        const popup = window.open(
            '/auth/google-popup',
            'google-auth',
            'popup,width=520,height=620,left=200,top=100',
        );
        if (!popup) {
            setError('Pop-up blocked — please allow pop-ups for this site and try again.');
            return;
        }
        popupRef.current = popup;

        const handleMessage = async (event: MessageEvent) => {
            if (event.origin !== window.location.origin) return;
            if (event.data?.type !== 'google-auth-complete') return;
            window.removeEventListener('message', handleMessage);
            clearInterval(pollClosed);
            popupRef.current = null;
            try {
                await refreshSession();
                router.replace(redirectTo);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Sign-in failed — please try again.');
            }
        };
        window.addEventListener('message', handleMessage);

        const pollClosed = setInterval(() => {
            if (popup.closed) {
                clearInterval(pollClosed);
                window.removeEventListener('message', handleMessage);
                popupRef.current = null;
            }
        }, 500);
    }
    ──────────────────────────────────────────────────────────────────────── */

    if (isInitializing || isAuthenticated) {
        return (
            <main id="main-content" className="max-w-[560px] mx-auto px-4 py-12">
                <div className="skeleton-block h-8 w-48 mb-4" />
                <div className="skeleton-block h-4 w-full mb-2" />
            </main>
        );
    }

    return (
        <main id="main-content" className="max-w-[560px] mx-auto px-4 py-12">
            <header className="mb-8 border-b-2 border-[var(--color-border)] pb-4">
                <h1
                    className="font-black tracking-tight leading-none mb-1"
                    style={{ fontSize: 'clamp(2rem, 5vw, 3rem)', fontFamily: 'var(--font-headline)' }}
                >
                    {heading ?? headingParam ?? (defaultSignIn ? 'Sign In' : 'Join The Commons')}
                </h1>
                <p className="text-sm italic text-[var(--color-text-muted)]">
                    {subheading ?? subheadingParam ?? (defaultSignIn
                        ? 'Enter your email to continue.'
                        : 'No password required — just tell us a little about you.')}
                </p>
            </header>

            {error && (
                <div
                    className="mb-6 p-2 border-2 border-[var(--color-accent)] text-[var(--color-accent)] text-sm font-bold"
                    role="alert"
                >
                    {error}
                </div>
            )}

            {/* ── Step 1: user type ───────────────────────────────────── */}
            {step === 'type' && (
                <section className="space-y-6">
                    <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1">
                        What best describes you?
                    </h2>
                    <div className="space-y-3">
                        {USER_TYPE_OPTIONS.map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                onClick={() => (userType === opt.value ? setStep('email') : setUserType(opt.value))}
                                aria-pressed={userType === opt.value}
                                className={`w-full text-left border p-4 transition-colors cursor-pointer ${
                                    userType === opt.value
                                        ? 'bg-[var(--color-text)] border-[var(--color-text)] text-[var(--color-bg)]'
                                        : 'bg-transparent border-[var(--color-border)] hover:bg-[var(--color-bg-alt)]'
                                }`}
                            >
                                <span className="block text-sm font-black uppercase tracking-wider">{opt.label}</span>
                                <span className="block text-xs mt-0.5 opacity-80">{opt.blurb}</span>
                            </button>
                        ))}
                    </div>
                    <div className="flex justify-between items-center pt-2">
                        <button
                            type="button"
                            onClick={goToLogin}
                            className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0"
                        >
                            Already have an account? <span className="font-bold">Sign in</span>
                        </button>
                        <Button variant="primary" onClick={() => setStep('email')}>
                            Continue
                        </Button>
                    </div>
                </section>
            )}

            {/* ── Step 2: email (+ name for business/venue) ───────────── */}
            {step === 'email' && (
                <form onSubmit={submitEmail} className="space-y-6">
                    {!defaultSignIn && isBusinessOrVenue && (
                        <Input
                            label={userType === 'VENUE' ? 'Venue Name' : 'Business Name'}
                            type="text"
                            value={businessName}
                            onChange={e => setBusinessName(e.target.value)}
                        />
                    )}
                    <Input
                        label="Email"
                        type="email"
                        autoComplete="email"
                        required
                        autoFocus
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                    />
                    <div className="flex justify-between items-center pt-2">
                        <button
                            type="button"
                            onClick={() => (defaultSignIn ? goToSignup() : setStep('type'))}
                            className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0"
                        >
                            {defaultSignIn ? 'Need an account? Sign up' : '← Back'}
                        </button>
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Continue'}
                        </Button>
                    </div>
                </form>
            )}

            {/* ── Step 3: preferences (optional) ──────────────────────── */}
            {step === 'prefs' && (
                <section className="space-y-6">
                    <div>
                        <h2 className="text-xs uppercase tracking-[0.2em] font-black text-[var(--color-accent)] border-b border-[var(--color-border-light)] pb-1 mb-3">
                            {isBusinessOrVenue ? 'What do you offer?' : 'What are you into?'}{' '}
                            <span className="text-[var(--color-text-muted)] font-bold">(optional)</span>
                        </h2>
                        <p className="text-sm text-[var(--color-text-muted)] mb-4">
                            You&rsquo;re all signed in. These are optional — pick a few to tailor your feed and
                            digest, or skip and set them later in your profile.
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
                    <div className="flex justify-between items-center pt-2">
                        <button
                            type="button"
                            onClick={() => router.replace(redirectTo)}
                            className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0"
                        >
                            Skip for now
                        </button>
                        <Button variant="primary" onClick={finishPrefs} disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Finish'}
                        </Button>
                    </div>
                </section>
            )}

            {/* ── Step: password (secured accounts) ───────────────────── */}
            {step === 'password' && (
                <form onSubmit={submitPassword} className="space-y-6">
                    <p className="text-sm text-[var(--color-text-muted)]">
                        This account is secured with a password. Enter it to sign in as{' '}
                        <span className="font-bold">{email.trim()}</span>.
                    </p>
                    <Input
                        label="Password"
                        type="password"
                        autoComplete="current-password"
                        required
                        autoFocus
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                    />
                    <div className="flex justify-between items-center pt-2">
                        <button
                            type="button"
                            onClick={() => { setPassword(''); setStep('email'); }}
                            className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] hover:text-[var(--color-accent)] underline bg-transparent border-none cursor-pointer p-0"
                        >
                            &larr; Use a different email
                        </button>
                        <Button type="submit" variant="primary" disabled={isLoading}>
                            {isLoading ? 'Please wait…' : 'Sign In'}
                        </Button>
                    </div>
                </form>
            )}

            {/* ── Google sign-in temporarily disabled — revisit later ───
            {step !== 'password' && (
                <>
                    <div className="my-6 flex items-center gap-3 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                        <span className="flex-1 border-t border-[var(--color-border-light)]" />
                        <span>or</span>
                        <span className="flex-1 border-t border-[var(--color-border-light)]" />
                    </div>
                    <button
                        type="button"
                        onClick={handleGoogle}
                        className="w-full flex items-center justify-center gap-3 border border-[var(--color-border)] py-3 px-4 text-xs uppercase tracking-wider font-bold hover:bg-[var(--color-bg-alt)] transition-colors cursor-pointer bg-transparent"
                    >
                        <GoogleIcon />
                        Continue with Google
                    </button>
                </>
            )}
            ──────────────────────────────────────────────────────────── */}
        </main>
    );
}

/* ── Google icon — paired with the disabled Google sign-in above ──────────
function GoogleIcon() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
        </svg>
    );
}
──────────────────────────────────────────────────────────────────────── */
