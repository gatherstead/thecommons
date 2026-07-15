import { inferAdditionalFields } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

const AUTH_URL =
  import.meta.env.VITE_BETTER_AUTH_URL || "http://localhost:3000";

// Mirrors the `user.additionalFields.user_type` shape declared in
// theCommonsWeb/src/lib/auth.ts. Declared inline (not imported) since that
// file pulls in server-only deps (drizzle db connection) unsuitable for a
// browser bundle.
export const authClient = createAuthClient({
  baseURL: AUTH_URL,
  plugins: [
    inferAdditionalFields({
      user: { user_type: { type: "string" } },
    }),
  ],
});

// Mint a short-lived JWT from an active Better Auth session cookie.
// Returns null if there is no session or the token endpoint fails.
export async function fetchJwt(): Promise<string | null> {
  try {
    const res = await fetch(`${AUTH_URL}/api/auth/token`, {
      credentials: "include",
    });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    return typeof data?.token === "string" ? data.token : null;
  } catch {
    return null;
  }
}

// Better Auth's jwt() plugin defaults to a 15-minute expirationTime (see
// better-auth/plugins/jwt/sign.ts) and this app never overrides it. Treat a
// cached token as fresh for well under that window so callers never hand the
// API a token that expires mid-flight — re-mint once the cache is older than
// this, not on every render.
export const JWT_FRESH_MS = 10 * 60 * 1000;
