import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  outputFileTracingIncludes: { "/api/*": ["./public/demo/manifest.json"] },
};
export default config;
