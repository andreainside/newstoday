import type { NextConfig } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;
if (!API_BASE) throw new Error("Missing NEXT_PUBLIC_API_BASE_URL");



const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
