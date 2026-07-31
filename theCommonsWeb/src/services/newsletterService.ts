// src/services/newsletterService.ts
//
// Public, login-free newsletter subscription endpoints. No auth token is
// ever sent here — these three calls are intentionally anonymous. See
// backend/urls.py (`newsletter/subscribe`, `newsletter/manage`) — both are
// APPEND_SLASH=False, so the paths below must not gain a trailing slash.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

export type NewsletterFrequency = 'WEEKLY' | 'MONTHLY';
export type ManageFrequency = NewsletterFrequency | 'NEVER';

export interface NewsletterSubscription {
    email: string;
    frequency: NewsletterFrequency;
}

export interface NewsletterManageState {
    email: string;
    frequency: ManageFrequency;
    is_active: boolean;
}

async function readError(res: Response, fallback: string): Promise<string> {
    try {
        const body = await res.json();
        if (body && typeof body.error === 'string') return body.error;
    } catch {
        // body wasn't JSON — fall through to the generic message
    }
    return fallback;
}

export async function subscribe(
    { email, frequency }: { email: string; frequency: NewsletterFrequency },
): Promise<NewsletterSubscription> {
    const res = await fetch(`${API_BASE}/newsletter/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, frequency }),
    });
    if (!res.ok) throw new Error(await readError(res, 'Failed to subscribe.'));
    return res.json();
}

export async function getSubscription(token: string): Promise<NewsletterManageState> {
    const res = await fetch(`${API_BASE}/newsletter/manage?token=${encodeURIComponent(token)}`);
    if (res.status === 404) throw new Error('NOT_FOUND');
    if (!res.ok) throw new Error(await readError(res, 'Failed to load your subscription.'));
    return res.json();
}

export async function updateSubscription(
    token: string,
    { frequency }: { frequency: ManageFrequency },
): Promise<NewsletterManageState> {
    const res = await fetch(`${API_BASE}/newsletter/manage?token=${encodeURIComponent(token)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frequency }),
    });
    if (res.status === 404) throw new Error('NOT_FOUND');
    if (!res.ok) throw new Error(await readError(res, 'Failed to update your subscription.'));
    return res.json();
}
