import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Fridge Logger",
  description: "Log your fridge contents with AI",
};

import { WsStatusIndicator } from "@/components/WsStatusIndicator";

// ... (rest of the file)

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 text-gray-900`}>
        <Providers>
          <main className="container mx-auto p-4">{children}</main>
          <WsStatusIndicator />
        </Providers>
      </body>
    </html>
  );
}