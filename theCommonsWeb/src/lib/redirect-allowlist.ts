// Pure, synchronous redirect-URL allowlist validator for the auth portal.
//
// Every portal flow ends by navigating to a `?redirect_to=…` value. Before
// that navigation happens, the value must pass through here so an attacker
// can't smuggle an open redirect (e.g. `?redirect_to=https://evil.com`) into
// a phishing link. This is a destination check, not CORS — it intentionally
// does not share code with the trusted-origin list in `auth.ts`.

const ALLOWED_HOSTS = new Set(['thecommons.town', 'www.thecommons.town']);
const ALLOWED_HOST_SUFFIX = '.thecommons.town';
const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1']);

/**
 * Resolve a raw `redirect_to` value to a safe destination.
 *
 * - Same-origin relative paths (single leading `/`, not `//`) pass through
 *   unchanged.
 * - Absolute URLs are allowed only when they resolve to an https
 *   *.thecommons.town origin, or an http(s) localhost/127.0.0.1 origin (dev).
 * - Anything else — including malformed input — falls back to `fallback`.
 *
 * Never throws; safe to call from both server and client code.
 */
export function resolveRedirect(raw: string | null, fallback = '/'): string {
    if (!raw) {
        return fallback;
    }

    // Relative path: allow a single leading slash, but reject protocol-relative
    // URLs (`//evil.com`) which browsers treat as absolute.
    if (raw.startsWith('/') && !raw.startsWith('//')) {
        return raw;
    }

    try {
        const url = new URL(raw);

        if (url.protocol !== 'http:' && url.protocol !== 'https:') {
            return fallback;
        }

        // Reject userinfo tricks like https://user@evil.com.
        if (url.username || url.password) {
            return fallback;
        }

        const hostname = url.hostname.toLowerCase();

        if (LOCAL_HOSTNAMES.has(hostname)) {
            return url.toString();
        }

        if (url.protocol !== 'https:') {
            return fallback;
        }

        if (ALLOWED_HOSTS.has(hostname) || hostname.endsWith(ALLOWED_HOST_SUFFIX)) {
            return url.toString();
        }

        return fallback;
    } catch {
        return fallback;
    }
}
