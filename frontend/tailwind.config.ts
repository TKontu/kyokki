import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: 'class',
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Clean industrial palette
        background: "var(--background)",
        foreground: "var(--foreground)",

        // UI Base colors - light theme
        ui: {
          bg: '#ffffff',
          'bg-secondary': '#f8f9fa',
          'bg-tertiary': '#f1f3f5',
          border: '#e9ecef',
          'border-strong': '#dee2e6',
          text: '#212529',
          'text-secondary': '#495057',
          'text-tertiary': '#868e96',
        },

        // Dark theme colors (applied via dark: variants)
        'ui-dark': {
          bg: '#1a1b1e',
          'bg-secondary': '#25262b',
          'bg-tertiary': '#2c2e33',
          border: '#373a40',
          'border-strong': '#424549',
          text: '#f8f9fa',
          'text-secondary': '#c1c2c5',
          'text-tertiary': '#909296',
        },

        // Primary accent (blue - clean and professional)
        primary: {
          50: '#e7f5ff',
          100: '#d0ebff',
          200: '#a5d8ff',
          300: '#74c0fc',
          400: '#4dabf7',
          500: '#339af0',
          600: '#228be6',
          700: '#1c7ed6',
          800: '#1971c2',
          900: '#1864ab',
        },

        // Expiry colors (adjusted for clean look)
        'expiry-expired': '#fa5252',   // red
        'expiry-urgent': '#fd7e14',    // orange
        'expiry-warning': '#fab005',   // yellow
        'expiry-ok': '#40c057',        // green

        // Status colors
        success: '#40c057',
        error: '#fa5252',
        warning: '#fab005',
        info: '#228be6',
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
      borderRadius: {
        // Clean, subtle roundness
        'ui': '8px',
        'ui-sm': '6px',
        'ui-lg': '12px',
      },
      boxShadow: {
        // Minimal, clean shadows
        'ui-xs': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'ui-sm': '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.08)',
        'ui': '0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.08)',
        'ui-md': '0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08)',
        // Dark mode shadows (slightly stronger)
        'ui-dark-xs': '0 1px 2px 0 rgb(0 0 0 / 0.3)',
        'ui-dark-sm': '0 1px 3px 0 rgb(0 0 0 / 0.4), 0 1px 2px -1px rgb(0 0 0 / 0.4)',
        'ui-dark': '0 4px 6px -1px rgb(0 0 0 / 0.4), 0 2px 4px -2px rgb(0 0 0 / 0.4)',
        'ui-dark-md': '0 10px 15px -3px rgb(0 0 0 / 0.4), 0 4px 6px -4px rgb(0 0 0 / 0.4)',
      },
      transitionDuration: {
        'ui': '150ms',
      },
    },
  },
  plugins: [],
};
export default config;
