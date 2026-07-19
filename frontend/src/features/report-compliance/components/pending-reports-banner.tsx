"use client";

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import { useMyCompliance } from "../hooks";

const DISMISS_KEY = "pending-reports-banner-dismissed";

/**
 * Login-check banner: when the employee has one or more previous working days
 * with attendance but no submitted report, show a dismissible reminder above the
 * page. Dismissal is per browser session (sessionStorage) so it reappears on the
 * next login but not on every navigation within the same session.
 */
export function PendingReportsBanner() {
  const { data } = useMyCompliance();
  const [dismissed, setDismissed] = React.useState(true);

  // Read the per-session dismissal flag after mount (avoids SSR mismatch).
  React.useEffect(() => {
    setDismissed(sessionStorage.getItem(DISMISS_KEY) === "1");
  }, []);

  const count = data?.pending_count ?? 0;
  // Warn-only: today's submitted report covers a different working fraction
  // than attendance implies (e.g. half-day report on a full present day).
  const mismatch = data?.fraction_mismatch_today === true;
  if (dismissed || (count < 1 && !mismatch)) return null;

  function dismiss() {
    sessionStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  return (
    <div className="border-b border-warning/30 bg-warning/10">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-2.5 md:px-8">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-hidden />
        <p className="min-w-0 flex-1 text-sm text-foreground">
          {count >= 1 &&
            `You have ${count} pending work report${count === 1 ? "" : "s"}.`}
          {count >= 1 && mismatch && " "}
          {mismatch &&
            `Today's report covers ${Math.round((data?.reported_work_fraction_today ?? 0) * 100)}% of the day but attendance shows ${Math.round((data?.attendance_work_fraction_today ?? 0) * 100)}% worked — it may be incomplete.`}
        </p>
        <Button size="sm" asChild>
          <Link href="/work-reports">Submit Pending Reports</Link>
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
      </div>
    </div>
  );
}
