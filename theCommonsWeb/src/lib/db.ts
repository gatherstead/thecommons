import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
    throw new Error('DATABASE_URL is required');
}

const globalForPool = globalThis as unknown as { __pgPool?: Pool };

const pool =
    globalForPool.__pgPool ??
    new Pool({
        connectionString,
        max: 10,
    });

if (process.env.NODE_ENV !== 'production') {
    globalForPool.__pgPool = pool;
}

export const db = drizzle(pool);
export { pool };
