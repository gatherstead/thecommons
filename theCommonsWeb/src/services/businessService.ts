import type { BusinessProfile, BusinessPayload } from '../models/businessModels';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

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

// Returns null when the business has no listing yet (404).
export async function getMyBusiness(token: string): Promise<BusinessProfile | null> {
    const res = await fetchWithRetry(`${API_BASE}/businesses/me`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error('Failed to fetch business listing');
    return res.json();
}

export async function createBusiness(token: string, payload: BusinessPayload): Promise<BusinessProfile> {
    const res = await fetch(`${API_BASE}/businesses`, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Failed to create business listing');
    return res.json();
}

export async function updateBusiness(
    token: string,
    uuid: string,
    patch: Partial<BusinessPayload>,
): Promise<BusinessProfile> {
    const res = await fetch(`${API_BASE}/businesses/${uuid}`, {
        method: 'PATCH',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error('Failed to update business listing');
    return res.json();
}

export async function deleteBusiness(token: string, uuid: string): Promise<void> {
    const res = await fetch(`${API_BASE}/businesses/${uuid}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to delete business listing');
}
