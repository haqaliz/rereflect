import type { Config } from "tailwindcss";
import sharedConfig from "@rereflect/ui/tailwind.config";

const config: Config = {
  ...sharedConfig,
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
    "../../packages/ui/src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    ...sharedConfig.theme,
    extend: {
      ...sharedConfig.theme?.extend,
      // The landing site runs Geist / Geist Mono, not the dashboard's
      // Montserrat / Ubuntu Mono. Override locally so Preflight and the
      // font-sans / font-mono utilities resolve to the loaded faces.
      fontFamily: {
        sans: ["var(--font-sans)", "-apple-system", "BlinkMacSystemFont", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
} as Config;

export default config;
