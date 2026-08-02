import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Standalone output: `next build` traces the minimal set of files needed to
  // run (server.js + a pruned node_modules) into .next/standalone. Lets the
  // Docker runtime stage (Dockerfile.frontend, `commons-runtime` target) copy
  // just that trace instead of the full node_modules — see Next.js docs on
  // "Output File Tracing" / standalone mode.
  output: 'standalone',
  serverExternalPackages: ['pg'],
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
      { protocol: 'http', hostname: '**' },
    ],
  },
};

export default nextConfig;
