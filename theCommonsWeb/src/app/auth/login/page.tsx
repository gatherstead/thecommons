import { redirect } from 'next/navigation';
import { headers } from 'next/headers';

// Legacy entry point — the apex app no longer renders its own login UI.
// Bounce straight to the portal's /signin, preserving any old params.
export default async function LoginPage({
    searchParams,
}: {
    searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
    const sp = await searchParams;
    const h = await headers();
    const host = h.get('host') ?? 'thecommons.town';
    const proto = host.startsWith('localhost') || host.startsWith('127.') ? 'http' : 'https';
    const apex = `${proto}://${host}`;

    const rawRedirect =
        typeof sp.redirect === 'string'
            ? sp.redirect
            : sp.intent === 'digest'
                ? '/profile#digest'
                : '/';
    const redirectTo = rawRedirect.startsWith('http') ? rawRedirect : `${apex}${rawRedirect}`;

    const authOrigin = process.env.NEXT_PUBLIC_BETTER_AUTH_URL ?? 'http://localhost:3000';
    redirect(`${authOrigin}/signin?redirect_to=${encodeURIComponent(redirectTo)}`);
}
