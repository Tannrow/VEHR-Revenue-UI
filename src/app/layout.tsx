import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VEHR Revenue OS",
  description: "Workflow-first revenue operating system for denials, claims, remits, and AI-guided recovery actions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
