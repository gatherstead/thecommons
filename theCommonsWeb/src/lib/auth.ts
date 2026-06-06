import { betterAuth } from 'better-auth';
import { drizzleAdapter } from 'better-auth/adapters/drizzle';
import { nextCookies } from 'better-auth/next-js';
import { jwt } from 'better-auth/plugins';
import { sql } from 'drizzle-orm';
import { db } from './db';
import * as schema from './auth-schema';
import { lazyAuth } from './lazy-auth-plugin';

export const auth = betterAuth({
    baseURL: process.env.BETTER_AUTH_URL ?? 'http://localhost:3000',
    secret: process.env.BETTER_AUTH_SECRET,
    database: drizzleAdapter(db, {
        provider: 'pg',
        schema: {
            user: schema.user,
            session: schema.session,
            account: schema.account,
            verification: schema.verification,
            jwks: schema.jwks,
        },
    }),
    // Neon pre-creates neon_auth.user.id as a real UUID column. Better Auth's
    // ID generator only reads advanced.database.generateId (not advanced.generateId).
    advanced: { database: { generateId: 'uuid' } },
    emailAndPassword: { enabled: true, autoSignIn: true },
    // Google sign-in temporarily disabled — revisit later. It returned
    // `invalid_code` and bypassed user-type selection during signup.
    // socialProviders: {
    //     google: {
    //         clientId: process.env.GOOGLE_CLIENT_ID!,
    //         clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    //     },
    // },
    user: {
        additionalFields: {
            user_type: {
                type: 'string',
                required: false,
                defaultValue: 'LOCAL',
                input: true,
            },
        },
    },
    plugins: [jwt(), lazyAuth(), nextCookies()],
    databaseHooks: {
        user: {
            create: {
                after: async (createdUser) => {
                    const userType =
                        (createdUser as { user_type?: string }).user_type ?? 'LOCAL';
                    await db.execute(sql`
                        INSERT INTO public.events_userprofile (uuid, user_id, user_type, primary_city, address, email_preference)
                        VALUES (gen_random_uuid(), ${createdUser.id}, ${userType}, '', '', 'NEVER')
                    `);
                },
            },
        },
    },
});
