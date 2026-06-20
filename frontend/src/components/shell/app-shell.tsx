"use client";

import * as React from "react";

import { Sidebar } from "@/components/shell/sidebar";
import { TopNav } from "@/components/shell/top-nav";
import { ComplianceGate } from "@/features/report-compliance/components/compliance-gate";
import { cn } from "@/lib/utils";

/** Authenticated frame: fixed sidebar (desktop) / off-canvas drawer (mobile). */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = React.useState(false);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      {/* Desktop sidebar */}
      <aside className="hidden md:block">
        <div className="sticky top-0 h-screen">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <div className="absolute left-0 top-0 h-full w-64 bg-background shadow-xl">
            <Sidebar onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-col">
        <TopNav onToggleSidebar={() => setDrawerOpen((v) => !v)} />
        <ComplianceGate />
        <main className={cn("mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8")}>
          {children}
        </main>
      </div>
    </div>
  );
}
