import { Suspense } from 'react';
import { and, eq, gt } from 'drizzle-orm';
import { ResetPasswordForm } from './ResetPasswordForm';
import { db } from '../../lib/db';
import { verification } from '../../lib/auth-schema';

// Better Auth's client SDK exposes no standalone "is this token still good"
// call — resetPassword() validates server-side but also consumes the token
// on success, and the GET /api/auth/reset-password/:token callback is a
// redirect-only route meant for the email link, not for AJAX use from here.
// So we check the verification table directly (read-only — this does not
// consume the token) and use that to decide what to render on mount. The
// resetPassword submit call remains the source of truth and stays wired up
// as a backstop for tokens that go stale between this check and submission.
async function checkTokenValidity(token: string | undefined): Promise<boolean | null> {
    if (!token) return null;

    const rows = await db
        .select({ id: verification.id })
        .from(verification)
        .where(
            and(
                eq(verification.identifier, `reset-password:${token}`),
                gt(verification.expiresAt, new Date()),
            ),
        )
        .limit(1);

    return rows.length > 0;
}

export default async function ResetPasswordPage({
    searchParams,
}: {
    searchParams: Promise<{ token?: string }>;
}) {
    const { token } = await searchParams;
    const tokenValid = await checkTokenValidity(token);

    return (
        <Suspense fallback={null}>
            <ResetPasswordForm initialTokenValid={tokenValid} />
        </Suspense>
    );
}
