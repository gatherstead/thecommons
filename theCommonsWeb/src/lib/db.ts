import { drizzle } from 'drizzle-orm/neon-http';
import { neon } from '@neondatabase/serverless';

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
    throw new Error('DATABASE_URL is required');
}

// Stateless HTTP driver — no persistent socket, so Neon compute can
// autosuspend between requests. See docs/broadcast.md-style rationale in the
// PR: this replaced drizzle-orm/node-postgres + pg.Pool, which held the
// connection open indefinitely.
const sql = neon(connectionString);

export const db = drizzle(sql);
