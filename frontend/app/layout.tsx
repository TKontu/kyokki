import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { AppShell } from "@/components/layout";
import {
  APPLE_ICON_PATH,
  BRAND_NAME,
  ICON_SIZES,
  iconPath,
  THEME_COLOR_DARK,
  THEME_COLOR_LIGHT,
} from "@/lib/brand";
import { Providers } from "./providers";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Kyokki - Kitchen Inventory System",
  description: "Smart kitchen inventory management - track all your groceries, dry goods, and consumables with receipt scanning",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: ICON_SIZES.map((size) => ({
      url: iconPath(size),
      sizes: `${size}x${size}`,
      type: "image/png",
    })),
    apple: APPLE_ICON_PATH,
  },
  // What actually makes Add to Home Screen launch full-screen on iPadOS; the manifest alone
  // is not enough on older iOS, and the two together are harmless (MVP-P2).
  appleWebApp: {
    capable: true,
    title: BRAND_NAME,
    statusBarStyle: "default",
  },
};

// viewportFit: without it env(safe-area-inset-*) resolves to 0 on the iPad, so the safe-area
// padding in the sheets, the toasts and the receipt footer would do nothing.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  // Lets the status bar, scrollbars and form controls follow the theme
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_COLOR_LIGHT },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLOR_DARK },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
