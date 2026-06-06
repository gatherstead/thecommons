const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type EmailPreference = 'WEEKLY' | 'MONTHLY' | 'NEVER';

export interface UserProfileData {
    id: string;
    email: string;
    business_name: string;
    user_type: string;
    primary_city: string;
    address: string;
    email_preference: EmailPreference;
    tags: string[];
    has_password: boolean;
}

// Retries transient failures (network errors / 5xx) — Neon serverless can
// cold-start, making the first request fail where a retry succeeds. 4xx
// responses are returned as-is since they won't self-heal.
async function fetchWithRetry(input: string, init: RequestInit, retries = 2): Promise<Response> {
    for (let attempt = 0; ; attempt++) {
        try {
            const res = await fetch(input, init);
            if (res.ok || res.status < 500 || attempt >= retries) return res;
        } catch (err) {
            if (attempt >= retries) throw err;
        }
        await new Promise(r => setTimeout(r, 300 * (attempt + 1)));
    }
}

export async function getProfile(token: string): Promise<UserProfileData> {
    const res = await fetchWithRetry(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to fetch profile');
    return res.json();
}

export async function updateProfile(
    token: string,
    patch: { email_preference?: EmailPreference; tags?: string[]; primary_city?: string; address?: string; user_type?: string },
): Promise<UserProfileData> {
    const res = await fetch(`${API_BASE}/auth/me`, {
        method: 'PATCH',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error('Failed to update profile');
    return res.json();
}
