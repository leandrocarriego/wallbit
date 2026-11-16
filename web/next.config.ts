import type { NextConfig } from "next";

// The browser only talks to Next; Next proxies /api to FastAPI (no CORS, one origin).
const apiTarget = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiTarget}/api/:path*` }];
  },
};

export default nextConfig;
