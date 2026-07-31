export type UserType = 'LOCAL' | 'BUSINESS' | 'VENUE';

export interface AuthUser {
    id: string;
    email: string;
    business_name: string;
    user_type: UserType;
}

export interface LoginPayload {
    email: string;
    password: string;
}

export interface SignupPayload {
    email: string;
    password: string;
    user_type?: UserType;
}
