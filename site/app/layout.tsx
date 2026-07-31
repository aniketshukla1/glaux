import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { SITE, asset } from "./config";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

const title = "Athena — a multi-agent swarm that proves its work";
const description =
  "A self-improving multi-agent swarm. Every action is signed onto a tamper-evident ledger, it writes its own tools at runtime, and it improves itself without being able to get worse.";

const ogImage = `${SITE}/images/console.png`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title,
  description,
  openGraph: { title, description, type: "website", images: [ogImage] },
  twitter: { card: "summary_large_image", title, description, images: [ogImage] },
  icons: { icon: asset("/favicon.svg") },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <Header />
        {children}
        <Footer />
      </body>
    </html>
  );
}
