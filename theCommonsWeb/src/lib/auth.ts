import { betterAuth } from 'better-auth';
import { drizzleAdapter } from 'better-auth/adapters/drizzle';
import { nextCookies } from 'better-auth/next-js';
import { jwt } from 'better-auth/plugins';
import { sql } from 'drizzle-orm';
import { db } from './db';
import * as schema from './auth-schema';

export const auth = betterAuth({
    database: drizzleAdapter(db, {
        provider: 'pg',
        schema,
    }),
    emailAndPassword: {
        enabled: true,
        autoSignIn: true,
    },
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
    plugins: [jwt(), nextCookies()],
    databaseHooks: {
        user: {
            create: {
                after: async (createdUser) => {
                    const userType =
                        (createdUser as { user_type?: string }).user_type ?? 'LOCAL';
                    await db.execute(sql`
                        INSERT INTO public.events_userprofile (uuid, user_id, user_type, primary_city, email_preference)
                        VALUES (gen_random_uuid(), ${createdUser.id}, ${userType}, '', 'WEEKLY')
                    `);
                },
            },
        },
    },
});
