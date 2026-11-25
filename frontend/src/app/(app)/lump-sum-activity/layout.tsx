import type { Metadata } from "next";

export const metadata: Metadata = { title: "Lump-sum Activity" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
