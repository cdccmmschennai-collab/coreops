"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CalendarClock, ChevronLeft, ChevronRight, X } from "lucide-react";

import { PageContainer } from "@/components/shell/page-container";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { isManagerial } from "@/lib/rbac";
import {
  LOGIN_BANNER_KEYS,
  dismissBanner,
  isBannerDismissed,
} from "@/lib/login-banners";

import { useMyDeliverableReminders } from "../hooks";
import {
  deliverableHref,
  dueInLabel,
  formatDueDate,
  selectLoginReminders,
} from "../reminders";

// Dismissal lasts for the current login only (reset on login/logout).
const DISMISS_KEY = LOGIN_BANNER_KEYS.deliverableDue;

/**
 * Login reminder for project Heads and members: planned deliverables due
 * within the next 3 days (IST, backend-derived), shown ONE AT A TIME,
 * nearest deadline first, with "1 of N" and Previous / Next - so ten due
 * deliverables are still a single line, not ten. "View Deliverable" opens the
 * one on screen. Independent of the pending-reports banner: both stack.
 */
export function DeliverableDueBanner() {
  const { data } = useMyDeliverableReminders();
  const { status, role } = useAuth();
  const router = useRouter();
  const [dismissed, setDismissed] = React.useState(true);
  const [index, setIndex] = React.useState(0);

  React.useEffect(() => {
    setDismissed(isBannerDismissed(DISMISS_KEY));
  }, []);

  const due = React.useMemo(() => selectLoginReminders(data ?? []), [data]);
  // Never for PMs. The query is disabled for them, but it shares its cache key
  // with the PM dashboard card / Deliverables page, so cached data would
  // otherwise leak into this banner - gate on the role explicitly.
  if (status !== "authenticated" || isManagerial(role)) return null;
  if (dismissed || due.length === 0) return null;

  // A refetch can shrink the list (e.g. one was completed) - stay in range.
  const current = Math.min(index, due.length - 1);
  const d = due[current];
  const total = due.length;

  function dismiss() {
    dismissBanner(DISMISS_KEY);
    setDismissed(true);
  }

  return (
    <div className="border-b border-warning/30 bg-warning/10">
      <PageContainer className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5">
        <CalendarClock className="h-4 w-4 shrink-0 text-warning" aria-hidden />
        <p className="min-w-0 flex-1 text-sm text-foreground" aria-live="polite">
          <span className="font-semibold">{dueInLabel(d.days_remaining ?? 0)}:</span>{" "}
          {d.name}
          {d.project_code && (
            <span className="text-muted-foreground"> ({d.project_code})</span>
          )}
          <span className="text-muted-foreground">
            {" "}- Planned Submission {formatDueDate(d.target_date)}
          </span>
        </p>

        {total > 1 && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={current === 0}
              onClick={() => setIndex(current - 1)}
              aria-label="Previous deliverable"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-[3.5rem] text-center text-xs tabular-nums text-muted-foreground">
              {current + 1} of {total}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={current === total - 1}
              onClick={() => setIndex(current + 1)}
              aria-label="Next deliverable"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <Button size="sm" onClick={() => router.push(deliverableHref(d.id))}>
          View Deliverable
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={dismiss}
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </Button>
      </PageContainer>
    </div>
  );
}
