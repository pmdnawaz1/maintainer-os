import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@maintainer-os/agents"],
  images: {
    remotePatterns: [
      { hostname: "avatars.githubusercontent.com" },
      { hostname: "github.com" },
    ],
  },
};

export default nextConfig;
