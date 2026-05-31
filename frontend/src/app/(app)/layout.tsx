"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { FullScreenLoader } from "@/components/feedback/full-screen-loader";
import { useAuth } from "@/features/auth/auth-provider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (status === "unauthenticated") {
      const next = encodeURIComponent(pathname);
      router.replace(`/login?next=${next}`);
    }
  }, [status, pathname, router]);

  if (status !== "authenticated") {
    return <FullScreenLoader />;
  }

  return <AppShell>{children}</AppShell>;
}
