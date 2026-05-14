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
    login: (payload: LoginPayload) => Promise<AuthUser>;
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

    const signup = useCallback(async (payload: SignupPayload) => {
        const signUpInput = {
            email: payload.email,
            password: payload.password,
            name: payload.business_name,
            user_type: payload.user_type,
        };
        const { data, error } = await authClient.signUp.email(
            signUpInput as Parameters<typeof authClient.signUp.email>[0],
        );
        if (error) throw new Error(error.message || 'Sign-up failed');
        const sessionUser = data?.user as BaSessionUser | undefined;
        if (!sessionUser) throw new Error('Sign-up returned no user');
        const jwt = await fetchJwt();
        setToken(jwt);
        const next = buildAuthUser(sessionUser, null, payload.user_type);
        setUser(next);
        return next;
    }, []);

    const refreshSession = useCallback(async () => {
        const result = await resolveSession();
        if (result) { setUser(result.user); setToken(result.token); }
        else { setUser(null); setToken(null); }
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
