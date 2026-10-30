import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.ELECTRON === "1" ? "export" : undefined,
  images: { unoptimized: process.env.ELECTRON === "1" },
};

export default nextConfig;
