// src/services/eventService.ts

import type { FrontendEvent, BackendEvent, EventPayload } from "../models/eventsModels";



const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';


const transformBackendEvent = (backendEvent: BackendEvent): FrontendEvent => {
    const dateObj = new Date(backendEvent.date);

    // Format time 
    const timeString = dateObj.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit'
    });

    // Format price
    const priceVal = parseFloat(backendEvent.price);
    const priceString = priceVal === 0 ? "Free Entry" : `$${priceVal.toFixed(2)}`;

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
    };
};

// --- GET ALL EVENTS ---
export const getEvents = async (): Promise<FrontendEvent[]> => {
    try {
        const response = await fetch(`${API_BASE}/events`, {
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
export const createEvent = async (eventData: EventPayload) => {
    const response = await fetch(`${API_BASE}/events/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(eventData),
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(JSON.stringify(errorData));
    }
    return await response.json();
};