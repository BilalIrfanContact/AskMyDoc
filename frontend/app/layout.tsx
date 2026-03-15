import type { Metadata } from "next";
import { Fraunces, Sora } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const sora = Sora({ subsets: ["latin"], variable: "--font-sora" });

export const metadata: Metadata = {
  title: "AskMyDoc",
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
        <script
          dangerouslySetInnerHTML={{
            __html: `
(() => {
  const stored = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const shouldUseDark = stored ? stored === "dark" : prefersDark;
  document.documentElement.classList.toggle("dark", shouldUseDark);
})();
            `
          }}
        />
        {children}
      </body>
    </html>
  );
}
