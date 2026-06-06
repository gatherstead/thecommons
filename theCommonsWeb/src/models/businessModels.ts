export interface BusinessProfile {
    uuid: string;
    business_name: string;
    description: string;
    tag_names: string[];
    service_area: string[];   // town slugs
    contact_email: string;
    contact_phone: string;
    is_published: boolean;
}

export interface BusinessPayload {
    business_name: string;
    description: string;
    tags: string[];
    service_area: string[];
    contact_email: string;
    contact_phone?: string;
    is_published: boolean;
}
