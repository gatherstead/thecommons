// src/services/eventService.ts

import type { FrontendEvent, BackendEvent, EventPayload, TownOption } from "../models/eventsModels";



const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
const API_KEY = process.env.NEXT_PUBLIC_THE_COMMONS_API_KEY || '';


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
        tags: backendEvent.tag_names || [], // Map tag_names -> tags
        date: dateObj,
        time: timeString,
        price: priceString,
        link: backendEvent.link || '',
        photo: backendEvent.photo,
    };
};

// --- GET ALL TOWNS ---
export const getTowns = async (): Promise<TownOption[]> => {
    try {
        const response = await fetch(`${API_BASE}/events/towns/`);
        if (!response.ok) throw new Error('Failed to fetch towns');
        return await response.json();
    } catch (error) {
        console.error('Error fetching towns:', error);
        return [];
    }
};

// --- GET ALL EVENTS ---
export const getEvents = async (params?: {
    after?: string;
    before?: string;
    include_past?: boolean;
}): Promise<FrontendEvent[]> => {
    try {
        const query = new URLSearchParams();
        if (params?.after) query.set('after', params.after);
        if (params?.before) query.set('before', params.before);
        if (params?.include_past) query.set('include_past', 'true');

        const qs = query.toString();
        const url = `${API_BASE}/events/${qs ? `?${qs}` : ''}`;

        const response = await fetch(url, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
        });

        if (!response.ok) {
            throw new Error('Failed to fetch events');
        }

        const data: BackendEvent[] = await response.json();

        return data.map(transformBackendEvent);
    } catch (error) {
        console.error('Error fetching events:', error);
        return [];
    }
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