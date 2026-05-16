/** @type {import('next').NextConfig} */

const isProd = process.env.NODE_ENV === "production";

const nextConfig = {
  reactStrictMode: true,

  // Static export for Cloudflare Pages
  // API calls go directly to the Render backend via NEXT_PUBLIC_API_URL
  output: "export",
  trailingSlash: true,

  // Disable image optimisation (not supported in static export)
  images: {
    unoptimized: true,
    domains: ["localhost", "reel.yourdomain.com"],
  },

  // In static export, rewrites are not supported.
  // All /api/* calls use NEXT_PUBLIC_API_URL directly (set in lib/api.ts).
  // The rewrites below are kept for local `npm run dev` only.
  ...(isProd
    ? {}
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000"}/api/:path*`,
            },
          ];
        },
      }),

  // Environment variables baked in at build time
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000",
    NEXT_PUBLIC_RAZORPAY_KEY: process.env.NEXT_PUBLIC_RAZORPAY_KEY || "",
  },
};

module.exports = nextConfig;
