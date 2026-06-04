"use client";

import * as React from "react";
import { Bell } from "lucide-react";

import { cn } from "@/lib/utils";
import { useUnreadCount } from "../hooks";
import { NotificationDropdown } from "./notification-dropdown";

export function NotificationBell() {
  const [open, setOpen] = React.useState(false);
  const { data } = useUnreadCount();
  const count = data?.count ?? 0;

  // Refresh unread count when dropdown opens
  React.useEffect(() => {
    if (open) {
      // handled by react-query refetchOnWindowFocus + invalidate on mark-read
    }
  }, [open]);

  return (
    <>
      <button
        aria-label="Notifications"
        className={cn(
          "relative flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          open && "bg-muted text-foreground",
        )}
        onClick={() => setOpen((v) => !v)}
      >
        <Bell className="h-[18px] w-[18px]" />
        {count > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold leading-none text-primary-foreground">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && <NotificationDropdown onClose={() => setOpen(false)} />}
    </>
  );
}
