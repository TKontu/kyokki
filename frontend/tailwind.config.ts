import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Expiry colors
        'expiry-expired': '#ef4444',   // red-500
        'expiry-urgent': '#f97316',    // orange-500
        'expiry-warning': '#eab308',   // yellow-500
        'expiry-ok': '#22c55e',        // green-500
        // Priority colors
        'priority-urgent': '#ef4444',
        'priority-normal': '#3b82f6',
        'priority-low': '#6b7280',
      },
      spacing: {
        // Touch targets for iPad
        'touch': '44px',
        'touch-lg': '56px',
      },
      minHeight: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      minWidth: {
        'touch': '44px',
        'touch-lg': '56px',
      },
      fontSize: {
        // Larger for iPad readability
        'ipad-sm': ['16px', '24px'],
        'ipad-base': ['18px', '28px'],
        'ipad-lg': ['20px', '30px'],
      },
    },
  },
  plugins: [],
};
export default config;
