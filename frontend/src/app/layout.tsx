import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";

import { env } from "@/lib/env";
import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  // Each top-level route segment's layout.tsx sets its own `title`, rendered
  // through this template as "CoreOps | Attendance". Pages without one fall
  // back to the bare product name.
  title: {
    default: env.productName,
    template: `${env.productName} | %s`,
  },
  description: "Workforce Management System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${sourceSerif.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
