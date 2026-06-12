'use client';

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
    type ReactNode,
} from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type {
    AuthUser,
    EnterPayload,
    EnterResult,
    LoginPayload,
    UserType,
} from '../models/authModels';
import { authClient } from '../lib/auth-client';

interface AuthContextValue {
    user: AuthUser | null;
    token: string | null;
    isAuthenticated: boolean;
    isInitializing: boolean;
    /** Lazy login/signup by email. Sets a session unless the account requires a password. */
    enter: (payload: EnterPayload) => Promise<EnterResult>;
    /** Password sign-in for accounts that have set one (the `requiresPassword` path). */
    login: (payload: LoginPayload) => Promise<AuthUser>;
    /** Secure a passwordless account by setting a password. */
    setPassword: (password: string) => Promise<void>;
    logout: () => Promise<void>;
    /** Re-validates the Better Auth session and refreshes user + token state.
     *  Called after Google popup OAuth and the email `enter` flow complete. */
    refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

interface ProfileResponse {
    id: string;
    email: string;
    business_name: string;
    user_type: UserType;
    has_password?: boolean;
}

async function fetchJwt(): Promise<string | null> {
    try {
        const res = await fetch('/api/auth/token', { credentials: 'include' });
        if (!res.ok) return null;
        const data = await res.json();
        return data.token ?? null;
    } catch {
        return null;
    }
}

async function fetchProfileFromDjango(jwt: string): Promise<ProfileResponse | null> {
    try {
        const res = await fetch(`${API_BASE}/events/me/profile`, {
            headers: { Authorization: `Bearer ${jwt}` },
        });
        if (!res.ok) return null;
        return (await res.json()) as ProfileResponse;
    } catch {
        return null;
    }
}

type BaSessionUser = {
    id: string;
    email: string;
    name?: string | null;
    user_type?: string;
};

function buildAuthUser(
    sessionUser: BaSessionUser,
    profile: ProfileResponse | null,
    fallbackUserType: UserType = 'LOCAL',
): AuthUser {
    return {
        id: sessionUser.id,
        email: profile?.email ?? sessionUser.email,
        business_name: profile?.business_name ?? sessionUser.name ?? '',
        user_type:
            profile?.user_type ??
            (sessionUser.user_type as UserType | undefined) ??
            fallbackUserType,
        hasPassword: profile?.has_password ?? false,
    };
}

// Resolves the Better Auth session and the Django JWT. The Django profile is
// NOT fetched here — it lives in the ['profile', token] query below.
async function resolveSession(): Promise<{ sessionUser: BaSessionUser; token: string } | null> {
    const sessionRes = await authClient.getSession();
    const sessionUser = sessionRes.data?.user as BaSessionUser | undefined;
    if (!sessionUser) return null;
    const jwt = await fetchJwt();
    if (!jwt) return null;
    return { sessionUser, token: jwt };
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const queryClient = useQueryClient();
    const [sessionUser, setSessionUser] = useState<BaSessionUser | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isResolvingSession, setIsResolvingSession] = useState(true);

    const profileQuery = useQuery({
        queryKey: ['profile', token],
        queryFn: () => fetchProfileFromDjango(token!),
        enabled: !!token,
    });

    // Derived, never stored: recombines the imperative session/token state with
    // the profile query so profile invalidations propagate without effects.
    const user = useMemo<AuthUser | null>(
        () =>
            sessionUser && token
                ? buildAuthUser(sessionUser, profileQuery.data ?? null)
                : null,
        [sessionUser, token, profileQuery.data],
    );

    // The profile-pending term keeps pages gated on user_type from rendering
    // with fallback values; the !!token guard matters because a disabled query
    // stays pending forever.
    const isInitializing = isResolvingSession || (!!token && profileQuery.isPending);

    useEffect(() => {
        let cancelled = false;
        resolveSession()
            .then(result => {
                if (cancelled) return;
                if (result) { setSessionUser(result.sessionUser); setToken(result.token); }
                else { setSessionUser(null); setToken(null); }
            })
            .finally(() => { if (!cancelled) setIsResolvingSession(false); });
        return () => { cancelled = true; };
    }, []);

    const refreshSession = useCallback(async () => {
        const result = await resolveSession();
        if (result) {
            setSessionUser(result.sessionUser);
            setToken(result.token);
            // Prefix match covers token rotation; forces a refetch when the
            // token is unchanged (e.g. user_type changed server-side).
            await queryClient.invalidateQueries({ queryKey: ['profile'] });
        } else {
            setSessionUser(null);
            setToken(null);
        }
    }, [queryClient]);

    const enter = useCallback(async (payload: EnterPayload): Promise<EnterResult> => {
        const res = await fetch('/api/auth/enter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.message || data.error || 'Could not continue.');
        }
        const result = (await res.json()) as EnterResult;
        // A session cookie was set unless the account needs a password first.
        if (!result.requiresPassword) {
            await refreshSession();
        }
        return result;
    }, [refreshSession]);

    const login = useCallback(async (payload: LoginPayload) => {
        const { data, error } = await authClient.signIn.email({
            email: payload.email,
            password: payload.password,
        });
        if (error) throw new Error(error.message || 'Sign-in failed');
        const nextSessionUser = data?.user as BaSessionUser | undefined;
        if (!nextSessionUser) throw new Error('Sign-in returned no user');
        const jwt = await fetchJwt();
        setSessionUser(nextSessionUser);
        setToken(jwt);
        // Seeds the ['profile', jwt] cache and preserves the "login resolves
        // with the built AuthUser" contract.
        const profile = jwt
            ? await queryClient.fetchQuery({
                  queryKey: ['profile', jwt],
                  queryFn: () => fetchProfileFromDjango(jwt),
              })
            : null;
        return buildAuthUser(nextSessionUser, profile);
    }, [queryClient]);

    const setPassword = useCallback(async (password: string) => {
        const res = await fetch('/api/auth/set-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ password }),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.error || 'Could not set password.');
        }
        queryClient.setQueryData<ProfileResponse | null>(
            ['profile', token],
            old => (old ? { ...old, has_password: true } : old),
        );
    }, [queryClient, token]);

    const logout = useCallback(async () => {
        try { await authClient.signOut(); } catch { /* best-effort */ }
        setSessionUser(null);
        setToken(null);
        queryClient.removeQueries({ queryKey: ['profile'] });
    }, [queryClient]);

    const value = useMemo<AuthContextValue>(
        () => ({
            user,
            token,
            isAuthenticated: !!user && !!token,
            isInitializing,
            enter,
            login,
            setPassword,
            logout,
            refreshSession,
        }),
        [user, token, isInitializing, enter, login, setPassword, logout, refreshSession],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
    return ctx;
}
