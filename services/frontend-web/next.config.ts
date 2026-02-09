import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker deployments
  output: "standalone",
  // Required for monorepo: tells Next.js to trace dependencies from the workspace root
  outputFileTracingRoot: path.join(import.meta.dirname, "../../"),
};

export default nextConfig;
