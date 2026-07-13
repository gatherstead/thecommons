import { createRequire } from 'module';

const require = createRequire(import.meta.url);

// eslint-config-next v16 ships native flat config arrays (CJS); import via createRequire.
const nextCoreWebVitals = require('eslint-config-next/core-web-vitals');
const nextTypescript = require('eslint-config-next/typescript');

export default [
    { ignores: ['dist/**'] },
    // next/core-web-vitals and next/typescript ship as flat config arrays.
    ...nextCoreWebVitals,
    ...nextTypescript,
    {
        rules: {
            // Components must use useAuth() from @/hooks/useAuth — not auth-client directly.
            'no-restricted-imports': [
                'error',
                {
                    paths: [
                        {
                            name: '@/lib/auth-client',
                            message:
                                'Use useAuth() from @/hooks/useAuth instead of importing auth-client directly.',
                        },
                    ],
                },
            ],
        },
    },
];
