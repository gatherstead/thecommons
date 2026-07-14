import { toNextJsHandler } from 'better-auth/next-js';
import type { NextRequest } from 'next/server';
import { auth, TRUSTED_ORIGINS } from '../../../../lib/auth';

export const runtime = 'nodejs';

const { GET: baseGET, POST: basePOST } = toNextJsHandler(auth);

// Better Auth doesn't set Access-Control-Allow-* headers on its own routes
// (only its MCP plugin does) — cross-origin callers like broadcastWeb need
// them added explicitly here, scoped to the same trustedOrigins list.
function corsHeaders(origin: string | null): HeadersInit {
    if (!origin || !TRUSTED_ORIGINS.includes(origin)) return {};
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        Vary: 'Origin',
    };
}

async function withCors(req: NextRequest, handler: (req: NextRequest) => Promise<Response>) {
    const res = await handler(req);
    const headers = new Headers(res.headers);
    for (const [key, value] of Object.entries(corsHeaders(req.headers.get('origin')))) {
        headers.set(key, value);
    }
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

export async function GET(req: NextRequest) {
    return withCors(req, baseGET);
}

export async function POST(req: NextRequest) {
    return withCors(req, basePOST);
}

export function OPTIONS(req: NextRequest) {
    return new Response(null, { status: 204, headers: corsHeaders(req.headers.get('origin')) });
}
