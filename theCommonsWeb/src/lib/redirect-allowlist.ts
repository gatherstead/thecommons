// Open-redirect defense for auth-portal pages that accept a `?redirect_to=`
// query param (login, verify-email, etc.). An attacker who controls that
// param can otherwise send a logged-in user to a phishing page that looks
// like a continuation of the auth flow. `resolveRedirect` validates the
// target against a fixed allowlist of thecommons.town hosts (mirroring the
// spirit of `BASE_TRUSTED_ORIGINS` in `src/lib/auth.ts`, though that list
// governs CORS/origin checks, not destination URLs) and falls back to a
// safe default on anything suspicious. Pure and synchronous so it can run
// on the server or the client.

const ALLOWED_HOSTS = new Set(['thecommons.town', 'www.thecommons.town']);
const ALLOWED_HOST_SUFFIX = '.thecommons.town';

function isLocalHost(hostname: string): boolean {
    return hostname === 'localhost' || hostname === '127.0.0.1';
}

function isAllowedAbsoluteUrl(url: URL): boolean {
    if (url.username || url.password) return false;

    if (isLocalHost(url.hostname)) {
        return url.protocol === 'http:' || url.protocol === 'https:';
    }

    const isCommonsHost =
        ALLOWED_HOSTS.has(url.host) || url.host.endsWith(ALLOWED_HOST_SUFFIX);
    return isCommonsHost && url.protocol === 'https:';
}

export function resolveRedirect(
    raw: string | null | undefined,
    fallback = '/',
): string {
    if (!raw || !raw.trim()) return fallback;

    // Protocol-relative URLs (`//evil.com`) resolve against the current
    // protocol in a browser, effectively acting as absolute URLs — reject
    // before the relative-path check below would wrongly accept them.
    if (raw.startsWith('//')) return fallback;

    if (raw.startsWith('/')) return raw;

    try {
        const url = new URL(raw);
        return isAllowedAbsoluteUrl(url) ? raw : fallback;
    } catch {
        return fallback;
    }
}
