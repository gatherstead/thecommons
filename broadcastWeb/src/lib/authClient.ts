import { createAuthClient } from "better-auth/react";

const AUTH_URL =
  import.meta.env.VITE_BETTER_AUTH_URL || "http://localhost:3000";

export const authClient = createAuthClient({
  baseURL: AUTH_URL,
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
