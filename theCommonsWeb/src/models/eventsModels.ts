export interface TownOption {
    slug: string;
    name: string;
}

export interface CategoryOption {
    slug: string;
    display_name: string;
}

// 1. Define what the Django API actually sends us
export interface PaginatedBackendEvents {
    count: number;
    next: string | null;
    previous: string | null;
    results: BackendEvent[];
}

export interface BackendEvent {
    uuid: string;
    title: string;
    town: string;
    venue: string;
    date: string; // ISO String: "2026-05-20T19:00:00Z"
    description: string;
    price: string; // Django DecimalField sends a string like "10.00" or number
    tag_names: string[];
    category_slugs: string[];
    photo: string | null;
    link: string;
    is_verified: boolean;
    source_name: string;
}

//format the frontend expects
export interface FrontendEvent {
    id: string;
    title: string;
    venue: string;
    date: Date;
    time: string;
    description: string;
    tags: string[];
    categories: string[];
    town: string;
    price: string;
    link: string;
    photo: string | null;
    isVerified: boolean;
    sourceName: string;
}

// Define the payload for creating events
export interface EventPayload {
    title: string;
    town: string;
    venue: string;
    date: string;
    description: string;
    price: number;
    tags: string[];
    link: string;
    category?: string;
}

export type MyEventStatus = 'pending' | 'approved' | 'rejected' | 'duplicate' | 'published';

export interface MyEventSummary {
    id: string;
    title: string;
    date: string | null;
    venue: string;
    status: MyEventStatus;
}