/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // Same-origin API: the browser calls /api/* on the frontend origin and Next.js
  // proxies it to the backend. In production the destination is the compose
  // service name (set via the API_INTERNAL_URL build arg); in `next dev` it is
  // the local uvicorn. Standalone output inlines this config at build time, so
  // the value must be known when the image is built.
  async rewrites() {
    const api = process.env.API_INTERNAL_URL ?? 'http://localhost:8000'
    return [{ source: '/api/:path*', destination: `${api}/api/:path*` }]
  },
};

export default nextConfig;
