import type { NextConfig } from "next";

const crmBackend = process.env.CRM_BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  distDir: process.env.CRM_NEXT_DIST_DIR || ".next",
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${crmBackend}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
