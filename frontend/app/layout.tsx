import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "react-hot-toast";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "ReelAI — AI-Powered Reel Editor",
  description: "Upload raw video. AI creates viral reels automatically. Real estate, food & product reels in seconds.",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "ReelAI" },
  openGraph: {
    title: "ReelAI — AI-Powered Reel Editor",
    description: "Create viral reels with AI. No editing skills needed.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0f",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
        <meta name="mobile-web-app-capable" content="yes" />
      </head>
      <body className={`${inter.variable} font-sans bg-surface-900 text-white antialiased`}>
        {children}
        <Toaster
          position="top-center"
          toastOptions={{
            style: { background: "#1a1a24", color: "#fff", border: "1px solid #2c2c3a" },
            success: { iconTheme: { primary: "#5c7cfa", secondary: "#fff" } },
          }}
        />
      </body>
    </html>
  );
}
