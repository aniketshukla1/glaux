import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

const title = "Athena — a multi-agent swarm that proves its work";
const description =
  "A self-improving multi-agent swarm. Every action is signed onto a tamper-evident ledger, it writes its own tools at runtime, and it improves itself without being able to get worse.";

export const metadata: Metadata = {
  metadataBase: new URL("https://athena-swarm.github.io"),
  title,
  description,
  openGraph: { title, description, type: "website", images: ["/images/console.png"] },
  twitter: { card: "summary_large_image", title, description, images: ["/images/console.png"] },
  icons: { icon: "/favicon.svg" },
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
