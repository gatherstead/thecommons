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
    LoginPayload,
    SignupPayload,
    UserType,
} from '../models/authModels';
import { authClient } from '../lib/auth-client';

interface AuthContextValue {
    user: AuthUser | null;
    token: string | null;
    isAuthenticated: boolean;
    isInitializing: boolean;
    /** Password sign-in for existing accounts. */
    login: (payload: LoginPayload) => Promise<AuthUser>;
    /** Creates a new passworded account and signs the user in. */
    signup: (payload: SignupPayload) => Promise<AuthUser>;
    logout: () => Promise<void>;
    /** Re-validates the Better Auth session and refreshes user + token state.
     *  Called after Google popup OAuth completes. */
    refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

interface ProfileResponse {
    id: string;
    email: string;
    business_name: string;
    user_type: UserType;
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

    const signup = useCallback(async (payload: SignupPayload) => {
        const { data, error } = await authClient.signUp.email({
            email: payload.email,
            password: payload.password,
            name: '',
            user_type: payload.user_type ?? 'LOCAL',
        });
        if (error) throw new Error(error.message || 'Could not create account.');
        const nextSessionUser = data?.user as BaSessionUser | undefined;
        if (!nextSessionUser) throw new Error('Sign-up returned no user');
        const jwt = await fetchJwt();
        setSessionUser(nextSessionUser);
        setToken(jwt);
        // Seeds the ['profile', jwt] cache and preserves the "signup resolves
        // with the built AuthUser" contract.
        const profile = jwt
            ? await queryClient.fetchQuery({
                  queryKey: ['profile', jwt],
                  queryFn: () => fetchProfileFromDjango(jwt),
              })
            : null;
        return buildAuthUser(nextSessionUser, profile, payload.user_type ?? 'LOCAL');
    }, [queryClient]);

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
            login,
            signup,
            logout,
            refreshSession,
        }),
        [user, token, isInitializing, login, signup, logout, refreshSession],
    );

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
    return ctx;
}
