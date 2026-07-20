"use client";

import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { Sidebar } from "@/components/shell/sidebar";
import { useSidebar } from "@/components/shell/sidebar-provider";
import { TopNav } from "@/components/shell/top-nav";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ComplianceGate } from "@/features/report-compliance/components/compliance-gate";

const EXPANDED_WIDTH = "240px";
const COLLAPSED_WIDTH = "72px";

/**
 * Authenticated frame: sidebar grid column (desktop) / off-canvas drawer (mobile).
 *
 * The sidebar is a real grid column rather than a fixed overlay, so it cannot
 * cover the content at any width. `--sidebar-width` is applied inline from the
 * persisted preference, which is already correct on the first authenticated
 * render — so the column never animates in from the wrong width.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { collapsed, toggleCollapsed } = useSidebar();

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="min-h-screen transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none md:grid md:grid-cols-[var(--sidebar-width)_minmax(0,1fr)]"
        style={{ "--sidebar-width": collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH } as React.CSSProperties}
      >
        <aside className="hidden overflow-hidden md:block">
          <div className="sticky top-0 h-screen">
            <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
          </div>
        </aside>

        <div className="flex min-w-0 flex-col">
          <TopNav />
          <ComplianceGate />
          <PageContainer as="main" className="flex-1 py-6">
            {children}
          </PageContainer>
        </div>
      </div>
    </TooltipProvider>
  );
}
