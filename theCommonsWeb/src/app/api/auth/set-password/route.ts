import { headers } from 'next/headers';
import { auth } from '@/lib/auth';
import { APIError } from 'better-auth/api';

export const runtime = 'nodejs';

const MIN_PASSWORD_LENGTH = 8;

export async function POST(req: Request) {
    let password: unknown;
    try {
        ({ password } = await req.json());
    } catch {
        return Response.json({ error: 'Invalid request body.' }, { status: 400 });
    }

    if (typeof password !== 'string' || password.length < MIN_PASSWORD_LENGTH) {
        return Response.json(
            { error: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.` },
            { status: 400 },
        );
    }

    try {
        await auth.api.setPassword({
            body: { newPassword: password },
            headers: await headers(),
        });
    } catch (e) {
        if (e instanceof APIError) {
            return Response.json(
                { error: e.message || 'Could not set password.' },
                { status: e.statusCode ?? 400 },
            );
        }
        return Response.json({ error: 'Could not set password.' }, { status: 500 });
    }

    return Response.json({ hasPassword: true });
}
