import type { Metadata } from "next";
import { Fraunces, Sora } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const sora = Sora({ subsets: ["latin"], variable: "--font-sora" });

export const metadata: Metadata = {
  title: "PDF AI Chatbot",
  description: "Upload a PDF and chat with it using AI."
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${fraunces.variable} ${sora.variable}`}>
      <body className="min-h-screen font-[var(--font-sora)]">
        {children}
      </body>
    </html>
  );
}
