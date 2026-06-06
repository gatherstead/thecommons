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

async function resolveSession(): Promise<{ user: AuthUser; token: string } | null> {
    const sessionRes = await authClient.getSession();
    const sessionUser = sessionRes.data?.user as BaSessionUser | undefined;
    if (!sessionUser) return null;
    const jwt = await fetchJwt();
    if (!jwt) return null;
    const profile = await fetchProfileFromDjango(jwt);
    return { user: buildAuthUser(sessionUser, profile), token: jwt };
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isInitializing, setIsInitializing] = useState(true);

    useEffect(() => {
        let cancelled = false;
        resolveSession()
            .then(result => {
                if (cancelled) return;
                if (result) { setUser(result.user); setToken(result.token); }
                else { setUser(null); setToken(null); }
            })
            .finally(() => { if (!cancelled) setIsInitializing(false); });
        return () => { cancelled = true; };
    }, []);

    const refreshSession = useCallback(async () => {
        const result = await resolveSession();
        if (result) { setUser(result.user); setToken(result.token); }
        else { setUser(null); setToken(null); }
    }, []);

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
        const sessionUser = data?.user as BaSessionUser | undefined;
        if (!sessionUser) throw new Error('Sign-in returned no user');
        const jwt = await fetchJwt();
        setToken(jwt);
        const profile = jwt ? await fetchProfileFromDjango(jwt) : null;
        const next = buildAuthUser(sessionUser, profile);
        setUser(next);
        return next;
    }, []);

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
        setUser(prev => (prev ? { ...prev, hasPassword: true } : prev));
    }, []);

    const logout = useCallback(async () => {
        try { await authClient.signOut(); } catch { /* best-effort */ }
        setUser(null);
        setToken(null);
    }, []);

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
