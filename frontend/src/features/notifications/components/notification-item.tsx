"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  CheckCircle,
  ClipboardList,
  Clock,
  FileText,
  FolderKanban,
  UserPlus,
  X,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Notification, NotificationSeverity } from "../types";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return "just now";
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30)  return `${d}d ago`;
  const mo = Math.floor(d / 30);
  return `${mo}mo ago`;
}

// ── icon + color per type ──────────────────────────────────────────────────

type ColorKey = "blue" | "green" | "red" | "amber" | "violet" | "slate";

const TYPE_CONFIG: Record<
  string,
  { Icon: React.ComponentType<{ className?: string }>; color: ColorKey }
> = {
  leave_submitted:       { Icon: FileText,      color: "blue" },
  leave_approved:        { Icon: CheckCircle,   color: "green" },
  leave_rejected:        { Icon: XCircle,       color: "red" },
  leave_cancelled:       { Icon: X,             color: "amber" },
  report_submitted:      { Icon: FileText,      color: "blue" },
  report_approved:       { Icon: CheckCircle,   color: "green" },
  report_rejected:       { Icon: XCircle,       color: "red" },
  project_assigned:      { Icon: FolderKanban,  color: "blue" },
  deliverable_planned:   { Icon: ClipboardList, color: "blue" },
  deliverable_date_updated:{ Icon: CalendarClock, color: "amber" },
  deliverable_completed: { Icon: CheckCircle,   color: "green" },
  calendar_event_created:{ Icon: CalendarDays,  color: "violet" },
  employee_created:      { Icon: UserPlus,      color: "green" },
  NUMERIC_BENCHMARK:     { Icon: AlertTriangle, color: "amber" },
  TASK_OVERDUE:          { Icon: Clock,         color: "red" },
};

const BG: Record<ColorKey, string> = {
  blue:   "bg-blue-50   text-blue-700",
  green:  "bg-emerald-50 text-emerald-700",
  red:    "bg-red-50    text-red-700",
  amber:  "bg-amber-50  text-amber-700",
  violet: "bg-violet-50 text-violet-700",
  slate:  "bg-slate-100 text-slate-700",
};

// Severity outranks the type-based color for ongoing-condition notifications
// (NUMERIC_BENCHMARK/TASK_OVERDUE) — CRITICAL always reads as urgent even if
// a new type is added later without updating TYPE_CONFIG.
const SEVERITY_COLOR: Partial<Record<NotificationSeverity, ColorKey>> = {
  WARNING: "amber",
  CRITICAL: "red",
};

function getConfig(type: string, severity?: NotificationSeverity) {
  const base = TYPE_CONFIG[type] ?? { Icon: FileText, color: "slate" as ColorKey };
  const color = (severity && SEVERITY_COLOR[severity]) ?? base.color;
  return { ...base, color };
}

// ── compact row (used in dropdown) ─────────────────────────────────────────

export function NotificationItemCompact({
  n,
  onMarkRead,
  onClose,
}: {
  n: Notification;
  onMarkRead?: (id: string) => void;
  onClose?: () => void;
}) {
  const router = useRouter();
  const { Icon, color } = getConfig(n.type, n.severity);
  const ago = timeAgo(n.created_at);

  function handleClick() {
    if (!n.is_read) onMarkRead?.(n.id);
    onClose?.();
    if (n.target_url) router.push(n.target_url);
  }

  return (
    <div
      role="button"
      tabIndex={0}
      className={cn(
        "flex cursor-pointer gap-2.5 px-4 py-3 transition-colors hover:bg-muted/40",
        !n.is_read && "bg-primary/[0.025]",
      )}
      onClick={handleClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(); }}
    >
      {/* unread dot */}
      <div className="flex w-2 shrink-0 items-start pt-1.5">
        {!n.is_read && (
          <span className="block h-2 w-2 rounded-full bg-primary" />
        )}
      </div>

      {/* icon */}
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
          BG[color],
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>

      {/* content */}
      <div className="min-w-0 flex-1">
        <p className={cn("text-[13px] leading-snug", !n.is_read ? "font-semibold" : "font-medium")}>
          {n.title}
        </p>
        <p className="mt-0.5 line-clamp-2 text-[12px] text-muted-foreground">
          {n.message}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground/70">{ago}</p>
      </div>
    </div>
  );
}

// ── full row (used in /notifications page) ─────────────────────────────────

export function NotificationItemFull({
  n,
  last,
  onMarkRead,
}: {
  n: Notification;
  last: boolean;
  onMarkRead?: (id: string) => void;
}) {
  const router = useRouter();
  const { Icon, color } = getConfig(n.type, n.severity);
  const ago = timeAgo(n.created_at);

  function handleNavigate() {
    if (!n.is_read) onMarkRead?.(n.id);
    if (n.target_url) router.push(n.target_url);
  }

  return (
    <div
      className={cn(
        "flex gap-3.5 px-5 py-4",
        !last && "border-b border-border",
        !n.is_read && "bg-primary/[0.025]",
        n.target_url && "cursor-pointer hover:bg-muted/40 transition-colors",
      )}
      onClick={n.target_url ? handleNavigate : undefined}
      role={n.target_url ? "button" : undefined}
      tabIndex={n.target_url ? 0 : undefined}
      onKeyDown={
        n.target_url
          ? (e) => { if (e.key === "Enter" || e.key === " ") handleNavigate(); }
          : undefined
      }
    >
      {/* unread dot */}
      <div className="flex w-2 shrink-0 items-start pt-2">
        {!n.is_read && (
          <span className="block h-2 w-2 rounded-full bg-primary" />
        )}
      </div>

      {/* icon */}
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
          BG[color],
        )}
      >
        <Icon className="h-[18px] w-[18px]" />
      </div>

      {/* content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-3">
          <span className={cn("text-sm", !n.is_read ? "font-semibold" : "font-medium")}>
            {n.title}
          </span>
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">{ago}</span>
        </div>
        <p className="mt-0.5 text-[13px] text-muted-foreground">{n.message}</p>
        {!n.is_read && (
          <button
            className="mt-2 text-[12px] text-primary hover:underline"
            onClick={(e) => { e.stopPropagation(); onMarkRead?.(n.id); }}
          >
            Mark as read
          </button>
        )}
      </div>
    </div>
  );
}
