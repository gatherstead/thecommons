import { betterAuth } from 'better-auth';
import { drizzleAdapter } from 'better-auth/adapters/drizzle';
import { nextCookies } from 'better-auth/next-js';
import { jwt } from 'better-auth/plugins';
import { sql } from 'drizzle-orm';
import { db } from './db';
import * as schema from './auth-schema';
import { lazyAuth } from './lazy-auth-plugin';

const BASE_TRUSTED_ORIGINS = [
    'https://thecommons.town',
    'https://www.thecommons.town',
    'https://broadcast.thecommons.town',
    'http://localhost:3000',
    'http://localhost:5173',
];

const extraOrigins = (process.env.BETTER_AUTH_TRUSTED_ORIGINS ?? '')
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);

// Better Auth's own trustedOrigins list only governs internal origin/redirect
// validation — it does not emit Access-Control-Allow-* response headers.
// Cross-origin callers (broadcastWeb, in dev or prod) need those set
// explicitly; see the route handler in app/api/auth/[...all]/route.ts.
export const TRUSTED_ORIGINS = [...BASE_TRUSTED_ORIGINS, ...extraOrigins];

const cookieDomain = process.env.BETTER_AUTH_COOKIE_DOMAIN;

export const auth = betterAuth({
    baseURL: process.env.BETTER_AUTH_URL ?? 'http://localhost:3000',
    secret: process.env.BETTER_AUTH_SECRET,
    trustedOrigins: TRUSTED_ORIGINS,
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
    // cookieDomain is only set in prod (.thecommons.town); in dev it is unset so
    // cookies remain localhost-scoped and SameSite=Lax (the better-auth default).
    advanced: {
        database: { generateId: 'uuid' },
        ...(cookieDomain
            ? {
                  crossSubDomainCookies: { enabled: true, domain: cookieDomain },
                  defaultCookieAttributes: { sameSite: 'none', secure: true, partitioned: false },
              }
            : {}),
    },
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
                    // This mirror INSERT must never block account creation: Better Auth
                    // runs this hook inside the signup transaction, so a throw here
                    // would roll back the just-inserted `account` credential row and
                    // leave a `user` with no way to sign in. ON CONFLICT DO NOTHING
                    // guards duplicate mirror rows; the try/catch guards everything
                    // else (schema/column drift, etc). A user may transiently exist
                    // without an events_userprofile row until backfilled — acceptable.
                    try {
                        await db.execute(sql`
                            INSERT INTO public.events_userprofile (uuid, user_id, user_type, primary_city, address, email_preference)
                            VALUES (gen_random_uuid(), ${createdUser.id}, ${userType}, '', '', 'NEVER')
                            ON CONFLICT DO NOTHING
                        `);
                    } catch (err) {
                        console.error(
                            `[auth] failed to mirror events_userprofile for user ${createdUser.id}:`,
                            err,
                        );
                    }
                },
            },
        },
    },
});
