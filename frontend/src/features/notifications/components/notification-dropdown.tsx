"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";

import { useMarkAllRead, useMarkRead, useNotifications } from "../hooks";
import { NotificationItemCompact } from "./notification-item";

interface Props {
  onClose: () => void;
}

export const NotificationDropdown = React.forwardRef<HTMLDivElement, Props>(
  function NotificationDropdown({ onClose }, ref) {
  const query = useNotifications({ limit: 8, offset: 0 });
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();

  const items = query.data?.items ?? [];
  const unreadCount = items.filter((n) => !n.is_read).length;

  async function handleMarkAll() {
    try {
      await markAll.mutateAsync();
      toast.success("All notifications marked as read");
    } catch {
      toast.error("Could not mark all as read");
    }
  }

  return (
    <>
      {/* panel — matches design: 380px, right-anchored, rounded-xl, shadow-lg.
          Click-outside / Escape / route-change closing is owned by the bell;
          no blocking backdrop, so clicks pass through to the page underneath. */}
      <div
        ref={ref}
        role="dialog"
        aria-label="Notifications"
        className="fixed right-4 top-[60px] z-50 flex max-h-[calc(100vh-80px)] w-[380px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-lg"
        style={{ animation: "notifIn 180ms ease-out" }}
      >
        {/* header */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-3.5">
          <span className="text-sm font-semibold">Notifications</span>
          {unreadCount > 0 && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
              {unreadCount} new
            </span>
          )}
          {unreadCount > 0 && (
            <button
              className="ml-auto text-[12px] text-primary hover:underline"
              onClick={() => void handleMarkAll()}
            >
              Mark all read
            </button>
          )}
        </div>

        {/* list */}
        <div className="flex-1 divide-y divide-border overflow-y-auto">
          {query.isLoading ? (
            <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
              Loading…
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              title="No notifications"
              description="When something needs your attention, it'll show up here."
            />
          ) : (
            items.map((n) => (
              <NotificationItemCompact
                key={n.id}
                n={n}
                onMarkRead={(id) => void markRead.mutateAsync(id)}
                onClose={onClose}
              />
            ))
          )}
        </div>

        {/* footer */}
        <div className="border-t border-border bg-muted/40 px-4 py-3 text-center">
          <Link
            href="/notifications"
            className="text-[13px] text-primary hover:underline"
            onClick={onClose}
          >
            View all →
          </Link>
        </div>
      </div>

      <style>{`
        @keyframes notifIn {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </>
  );
});
