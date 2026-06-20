import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@maintainer-os/agents", "@maintainer-os/types"],
  images: {
    remotePatterns: [
      { hostname: "avatars.githubusercontent.com" },
      { hostname: "github.com" },
    ],
  },
};

export default nextConfig;
