import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AskMyDoc: Q&A for financial filings",
  description: "Ask questions about 10-Ks, 10-Qs and annual reports and see the passages each answer comes from."
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
