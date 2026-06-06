export type UserType = 'LOCAL' | 'BUSINESS' | 'VENUE';

export interface AuthUser {
    id: string;
    email: string;
    business_name: string;
    user_type: UserType;
    /** Whether the account is secured with a password. Lazy accounts start false. */
    hasPassword: boolean;
}

export interface EnterPayload {
    email: string;
    user_type?: UserType;
    name?: string;
}

export interface EnterResult {
    isNew: boolean;
    /** True when the account has a password set — caller must collect it and sign in. */
    requiresPassword: boolean;
}

export interface LoginPayload {
    email: string;
    password: string;
}
