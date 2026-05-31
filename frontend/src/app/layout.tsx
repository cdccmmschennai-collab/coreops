import type { Metadata } from "next";
import "./globals.css";
import { productName } from "@/lib/config";

export const metadata: Metadata = {
  title: productName,
  description: "Workforce Management System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
