"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { SidebarProvider } from "@/components/shell/sidebar-provider";
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

  // Sits OUTSIDE AppShell so AppShell, Sidebar and TopNav can all consume the
  // preference in a later phase; inside the auth gate so it never wraps login
  // and always mounts with an authenticated identifier available.
  return (
    <SidebarProvider>
      <AppShell>{children}</AppShell>
    </SidebarProvider>
  );
}
