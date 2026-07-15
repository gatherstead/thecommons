import Redis from 'ioredis';

// Backs better-auth's `secondaryStorage` (sessions), so session reads/writes
// never touch Neon. The backend already uses Redis DB 0 (Celery broker/
// results) and DB 1 (Django cache) — this MUST use a different db index so
// keys don't collide. Expected value: same Redis host as the backend, db 2,
// e.g. `redis://localhost:6379/2` in dev.
const connectionString = process.env.BETTER_AUTH_REDIS_URL ?? process.env.REDIS_URL;
if (!connectionString) {
    throw new Error('BETTER_AUTH_REDIS_URL (or REDIS_URL) is required');
}

const globalForRedis = globalThis as unknown as { __authRedis?: Redis };

const redis = globalForRedis.__authRedis ?? new Redis(connectionString);

if (process.env.NODE_ENV !== 'production') {
    globalForRedis.__authRedis = redis;
}

export { redis };
