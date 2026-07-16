import { redirect } from 'next/navigation';

export default async function AuthPage({
    searchParams,
}: {
    searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
    const sp = await searchParams;
    const explicitRedirect = typeof sp.redirect === 'string' ? sp.redirect : undefined;
    const intent = typeof sp.intent === 'string' ? sp.intent : undefined;
    const redirectTo = explicitRedirect ?? (intent === 'digest' ? '/profile#digest' : undefined);

    redirect(redirectTo ? `/join?redirect_to=${encodeURIComponent(redirectTo)}` : '/join');
}
