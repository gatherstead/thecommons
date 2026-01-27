// 1. Define what the Django API actually sends us
export interface BackendEvent {
    uuid: string;
    title: string;
    town: string;
    venue: string;
    date: string; // ISO String: "2026-05-20T19:00:00Z"
    description: string;
    price: string; // Django DecimalField sends a string like "10.00" or number
    tag_names: string[];
    photo: string | null;
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
    town: string;
    price: string;
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
}