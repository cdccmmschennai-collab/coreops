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
 * The sidebar is a real grid column, so it cannot cover the content at any
 * width — the column reserves the rail's width whatever the rail itself is
 * doing. `--sidebar-width` is applied inline from the persisted preference,
 * which is already correct on the first authenticated render — so the column
 * never animates in from the wrong width, and the rail laid over it inherits
 * the same variable and stays exactly as wide as the space reserved for it.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { collapsed, toggleCollapsed } = useSidebar();

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="min-h-screen transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none md:grid md:grid-cols-[var(--sidebar-width)_minmax(0,1fr)]"
        style={{ "--sidebar-width": collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH } as React.CSSProperties}
      >
        {/* `fixed`, deliberately, and NOT `sticky`.

            The rail is pinned from the very first pixel of scroll - it has no
            "scroll along, then stick" phase, because its containing block began
            at document y=0 and its offset was `top: 0`. Sticky buys nothing for
            an element like that; all it adds is the work of re-deriving the
            same position on every single scroll frame. When that correction
            lands a frame behind the compositor - which is what was happening -
            the rail visibly drags in the scroll direction and snaps back, which
            is the shake: down when scrolling down, up when scrolling up.

            A fixed element is not part of the scrolling contents at all, so
            there is no per-frame position to get wrong and nothing to lag. It
            is the correct positioning scheme for "must not move while the
            document scrolls", not a workaround for one.

            It still cannot cover the content: the grid column below reserves
            exactly `--sidebar-width`, and the rail is laid over that reserved
            space (`left-0`, same width, same 200ms ease-out so the collapse
            animation stays in step with the column). `inset-y-0` also means the
            rail - and its border-r - is always exactly viewport height, so the
            separator can never run out at the bottom of a long page the way a
            sticky element eventually does. */}
        <aside className="hidden md:block">
          <div className="fixed inset-y-0 left-0 w-[var(--sidebar-width)] transition-[width] duration-200 ease-out motion-reduce:transition-none">
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
