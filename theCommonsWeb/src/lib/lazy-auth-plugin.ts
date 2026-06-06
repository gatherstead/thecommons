import type { BetterAuthPlugin } from 'better-auth';
import { APIError, createAuthEndpoint } from 'better-auth/api';
import { setSessionCookie } from 'better-auth/cookies';

const USER_TYPES = ['LOCAL', 'BUSINESS', 'VENUE'];

interface EnterBody {
    email?: string;
    user_type?: string;
    name?: string;
}

/**
 * Lazy account creation: a single `/enter` endpoint that logs users in by email
 * alone. New emails create a passwordless account + session on the spot; existing
 * passwordless accounts get a fresh session; accounts that have set a password are
 * asked for it instead (handled client-side via the normal email+password sign-in).
 */
export const lazyAuth = () =>
    ({
        id: 'lazy-auth',
        endpoints: {
            enter: createAuthEndpoint(
                '/enter',
                { method: 'POST' },
                async (ctx) => {
                    const body = (ctx.body ?? {}) as EnterBody;
                    const email = (body.email ?? '').trim().toLowerCase();
                    if (!email || !email.includes('@')) {
                        throw new APIError('BAD_REQUEST', {
                            message: 'A valid email is required.',
                        });
                    }

                    const existing = await ctx.context.internalAdapter.findUserByEmail(
                        email,
                        { includeAccounts: true },
                    );

                    if (existing) {
                        const secured = existing.accounts.some(
                            (a) => a.providerId === 'credential' && a.password,
                        );
                        if (secured) {
                            return ctx.json({ isNew: false, requiresPassword: true });
                        }
                        const session = await ctx.context.internalAdapter.createSession(
                            existing.user.id,
                        );
                        if (!session) {
                            throw new APIError('INTERNAL_SERVER_ERROR', {
                                message: 'Could not create session.',
                            });
                        }
                        await setSessionCookie(ctx, { session, user: existing.user });
                        return ctx.json({ isNew: false, requiresPassword: false });
                    }

                    const requested = (body.user_type ?? 'LOCAL').toUpperCase();
                    const userType = USER_TYPES.includes(requested) ? requested : 'LOCAL';

                    const newUser = await ctx.context.internalAdapter.createUser({
                        email,
                        name: (body.name ?? '').trim(),
                        emailVerified: false,
                        user_type: userType,
                        createdAt: new Date(),
                        updatedAt: new Date(),
                    });
                    if (!newUser) {
                        throw new APIError('UNPROCESSABLE_ENTITY', {
                            message: 'Could not create account.',
                        });
                    }
                    const session = await ctx.context.internalAdapter.createSession(
                        newUser.id,
                    );
                    if (!session) {
                        throw new APIError('INTERNAL_SERVER_ERROR', {
                            message: 'Could not create session.',
                        });
                    }
                    await setSessionCookie(ctx, { session, user: newUser });
                    return ctx.json({ isNew: true, requiresPassword: false });
                },
            ),
        },
    }) satisfies BetterAuthPlugin;
