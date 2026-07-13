"use client";

import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { Pagination } from "@/components/data/pagination";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { useUrlState } from "@/lib/use-url-state";

import { useMarkAllRead, useMarkRead, useNotifications } from "../hooks";
import { NotificationItemFull } from "./notification-item";

const LIMIT = 20;

export function NotificationList() {
  // Tab + page persist in the URL so opening a notification's target and coming
  // back returns to the same tab/page.
  const [tab, setTab] = useUrlState("tab", "all");
  const [offsetStr, setOffsetStr] = useUrlState("offset", "0");
  const offset = Math.max(0, Number(offsetStr) || 0);
  const setOffset = (o: number) => setOffsetStr(String(o));

  const query = useNotifications({
    unread_only: tab === "unread",
    limit: LIMIT,
    offset,
  });
  const markRead  = useMarkRead();
  const markAll   = useMarkAllRead();

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const unreadInList = items.filter((n) => !n.is_read).length;

  async function handleMarkAll() {
    try {
      await markAll.mutateAsync();
      toast.success("All notifications marked as read");
      setOffset(0);
    } catch {
      toast.error("Could not mark all as read");
    }
  }

  async function handleMarkRead(id: string) {
    try {
      await markRead.mutateAsync(id);
    } catch {
      toast.error("Could not mark notification as read");
    }
  }

  return (
    <>
      <PageHeader
        title="Notifications"
        subtitle={`${total} notification${total !== 1 ? "s" : ""} · in-app only`}
        actions={
          unreadInList > 0 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleMarkAll()}
              disabled={markAll.isPending}
            >
              Mark all read
            </Button>
          ) : undefined
        }
      />

      <Tabs
        className="mb-4"
        value={tab}
        onChange={(v) => { setTab(v as "all" | "unread"); setOffset(0); }}
        items={[
          { value: "all",    label: "All",    count: total },
          { value: "unread", label: "Unread", count: items.filter((n) => !n.is_read).length },
        ]}
      />

      {query.isLoading ? (
        <TableSkeleton rows={5} cols={1} />
      ) : (
        <Card>
          <CardContent className="p-0">
            {items.length === 0 ? (
              <EmptyState
                title="No notifications here"
                description="When something needs your attention, it'll show up here."
              />
            ) : (
              <>
                {items.map((n, i) => (
                  <NotificationItemFull
                    key={n.id}
                    n={n}
                    last={i === items.length - 1}
                    onMarkRead={handleMarkRead}
                  />
                ))}
                {total > LIMIT && (
                  <div className="border-t border-border p-4">
                    <Pagination
                      total={total}
                      limit={LIMIT}
                      offset={offset}
                      onPageChange={setOffset}
                    />
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
