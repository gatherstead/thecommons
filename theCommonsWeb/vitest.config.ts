import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Mirrors the `@/*` -> `./src/*` mapping in tsconfig.json.
const alias = { '@': fileURLToPath(new URL('./src', import.meta.url)) };

export default defineConfig({
    resolve: { alias },
    test: {
        projects: [
            {
                resolve: { alias },
                test: {
                    name: 'fast',
                    environment: 'node',
                    include: ['src/**/*.fast.test.{ts,tsx}'],
                },
            },
            {
                resolve: { alias },
                test: {
                    name: 'db',
                    environment: 'jsdom',
                    include: ['src/**/*.db.test.{ts,tsx}'],
                    setupFiles: ['./vitest.setup.ts'],
                },
            },
        ],
    },
});
