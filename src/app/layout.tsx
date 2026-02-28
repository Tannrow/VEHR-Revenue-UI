import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VEHR Revenue OS",
  description: "Revenue operating system UI for the VEHR platform",
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
