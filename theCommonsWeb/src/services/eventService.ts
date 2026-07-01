// src/services/eventService.ts

import type { FrontendEvent, BackendEvent, PaginatedBackendEvents, EventPayload, TownOption, CategoryOption, MyEventSummary } from "../models/eventsModels";

export interface EventsPage {
    results: FrontendEvent[];
    next: string | null;
    previous: string | null;
    count: number;
}



const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
const API_KEY = process.env.NEXT_PUBLIC_THE_COMMONS_API_KEY || '';

// Build a descriptive Error from a failed response so console logs show the real
// cause (status + body) instead of a generic "failed" message. A backend
// misconfig (e.g. DisallowedHost 400) otherwise looks identical to "0 events".
const httpError = async (method: string, url: string, response: Response): Promise<Error> => {
    const body = await response.text().catch(() => '');
    const snippet = body ? `: ${body.slice(0, 300)}` : '';
    return new Error(`${method} ${url} -> ${response.status} ${response.statusText}${snippet}`);
};

const transformBackendEvent = (backendEvent: BackendEvent): FrontendEvent => {
    const dateObj = new Date(backendEvent.date);

    // Format time 
    const timeString = dateObj.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit'
    });

    // Format price
    const priceVal = backendEvent.price == null ? null : parseFloat(backendEvent.price);
    const priceString =
        priceVal == null || priceVal < 0 ? "Not Listed" :
        priceVal === 0 ? "Free" :
        `$${priceVal.toFixed(2)}`;

    return {
        id: backendEvent.uuid, // Map uuid -> id
        title: backendEvent.title,
        venue: backendEvent.venue,
        town: backendEvent.town,
        description: backendEvent.description,
        tags: backendEvent.tag_names || [],
        categories: backendEvent.category_slugs || [],
        date: dateObj,
        time: timeString,
        price: priceString,
        link: backendEvent.link || '',
        photo: backendEvent.photo,
        isVerified: backendEvent.is_verified ?? false,
        sourceName: backendEvent.source_name ?? '',
    };
};

// --- GET ALL TOWNS ---
export const getTowns = async (): Promise<TownOption[]> => {
    try {
        const url = `${API_BASE}/events/towns/`;
        const response = await fetch(url);
        if (!response.ok) throw await httpError('GET', url, response);
        return await response.json();
    } catch (error) {
        console.error('Error fetching towns:', error);
        return [];
    }
};

// --- GET ALL CATEGORIES ---
export const getCategories = async (): Promise<CategoryOption[]> => {
    try {
        const url = `${API_BASE}/events/categories/`;
        const response = await fetch(url);
        if (!response.ok) throw await httpError('GET', url, response);
        return await response.json();
    } catch (error) {
        console.error('Error fetching categories:', error);
        return [];
    }
};

// --- GET ALL EVENTS ---
export const getEvents = async (params?: {
    after?: string;
    before?: string;
    include_past?: boolean;
    window?: 'past';
    pageUrl?: string;
    category?: string;
}): Promise<EventsPage> => {
    try {
        let url: string;
        if (params?.pageUrl) {
            url = params.pageUrl;
        } else {
            const query = new URLSearchParams();
            if (params?.after) query.set('after', params.after);
            if (params?.before) query.set('before', params.before);
            if (params?.include_past) query.set('include_past', 'true');
            if (params?.window) query.set('window', params.window);
            if (params?.category) query.set('category', params.category);
            const qs = query.toString();
            url = `${API_BASE}/events/${qs ? `?${qs}` : ''}`;
        }

        const response = await fetch(url, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
            throw await httpError('GET', url, response);
        }

        const data: PaginatedBackendEvents = await response.json();
        return {
            results: data.results.map(transformBackendEvent),
            next: data.next,
            previous: data.previous,
            count: data.count,
        };
    } catch (error) {
        console.error('Error fetching events:', error);
        return { results: [], next: null, previous: null, count: 0 };
    }
};

// --- GET ONE EVENT BY UUID ---
export const getEvent = async (uuid: string): Promise<FrontendEvent | null> => {
    try {
        const response = await fetch(`${API_BASE}/events/${uuid}`);
        if (!response.ok) return null;
        const data: BackendEvent = await response.json();
        return transformBackendEvent(data);
    } catch (error) {
        console.error('Error fetching event:', error);
        return null;
    }
};

// --- GET MY EVENTS (authenticated business user) ---
export const getMyEvents = async (token: string): Promise<MyEventSummary[]> => {
    const res = await fetch(`${API_BASE}/events/me/events`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to fetch your events');
    return res.json();
};

// --- STAGED EVENT MANAGEMENT (owner only) ---

export interface StagedEventDetail {
    id: number;
    title: string;
    venue: string;
    town: string;
    date: string | null;
    description: string;
    price: string;
    link: string;
    tags: string[];
    status: string;
}

export const getStagedEvent = async (token: string, eventId: string): Promise<StagedEventDetail> => {
    const res = await fetch(`${API_BASE}/events/staged/${eventId}`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to fetch event details');
    return res.json();
};

export const updateStagedEvent = async (
    token: string,
    eventId: string,
    patch: Partial<{ title: string; venue: string; town: string; date: string; description: string; price: string | null; link: string; tags: string[] }>,
): Promise<void> => {
    const res = await fetch(`${API_BASE}/events/staged/${eventId}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error('Failed to update event');
};

export const deleteStagedEvent = async (token: string, eventId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/events/staged/${eventId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to delete event');
};

export const deletePublishedEvent = async (token: string, eventId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/events/${eventId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to delete event');
};

// --- CREATE EVENT ---
export const createEvent = async (eventData: EventPayload, authToken?: string | null) => {
    const response = await fetch(`${API_BASE}/events/create`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken || API_KEY}`,
        },
        body: JSON.stringify(eventData),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(JSON.stringify(errorData));
    }
    return await response.json();
};