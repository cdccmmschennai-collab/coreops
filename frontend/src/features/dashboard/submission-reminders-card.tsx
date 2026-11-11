"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DeadlineBadge } from "@/features/project-deliverables/components/deadline-badge";
import { useAllDeliverables } from "@/features/project-deliverables/hooks";
import {
  daysRemainingLabel,
  deliverableHref,
  formatDueDate,
  selectReminderRows,
} from "@/features/project-deliverables/reminders";
import type { DeadlineState, Deliverable } from "@/features/project-deliverables/types";
import { cn } from "@/lib/utils";

/** Rows shown before "+N more" - keeps the card a dashboard card, not a page. */
const MAX_ROWS = 5;

// ── per-state styling (state itself always comes from the backend) ──────────

const ACCENT: Record<DeadlineState, string> = {
  overdue: "bg-destructive",
  due_today: "bg-warning",
  urgent: "bg-warning",
  due_soon: "bg-warning/50",
  on_track: "bg-border",
  no_deadline: "bg-border",
  completed: "bg-success",
};

const ROW_TINT: Partial<Record<DeadlineState, string>> = {
  overdue: "bg-destructive/[0.04]",
  due_today: "bg-warning/[0.06]",
};

const DAYS_TEXT: Record<DeadlineState, string> = {
  overdue: "text-destructive font-semibold",
  due_today: "text-warning font-semibold",
  urgent: "text-warning font-semibold",
  due_soon: "text-warning font-medium",
  on_track: "text-muted-foreground",
  no_deadline: "text-muted-foreground",
  completed: "text-success",
};

// ── one reminder row ────────────────────────────────────────────────────────

function ReminderRow({ d }: { d: Deliverable }) {
  const project = d.project_code ?? d.project_name ?? "Project";
  const days = daysRemainingLabel(d);
  return (
    <li>
      <Link
        href={deliverableHref(d.id)}
        aria-label={`View deliverable ${d.name}, project ${project}, ${days}`}
        data-state={d.deadline_state}
        className={cn(
          "group relative flex items-center gap-3 py-2.5 pl-4 pr-3 transition-colors hover:bg-secondary focus-visible:bg-secondary focus-visible:outline-none",
          ROW_TINT[d.deadline_state],
        )}
      >
        <span
          className={cn("absolute inset-y-1.5 left-0 w-[3px] rounded-r", ACCENT[d.deadline_state])}
          aria-hidden
        />

        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground" title={d.name}>
            {d.name}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <span className="truncate" title={d.project_name ?? undefined}>
              Project <span className="font-mono font-semibold text-foreground">{project}</span>
            </span>
            <span className="inline-flex items-center gap-1 tabular">
              <CalendarDays className="h-3 w-3" aria-hidden />
              Due{" "}
              <span className="font-semibold text-foreground">{formatDueDate(d.target_date)}</span>
            </span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <DeadlineBadge state={d.deadline_state} />
          <span className={cn("text-xs tabular", DAYS_TEXT[d.deadline_state])}>{days}</span>
        </div>

        <span className="hidden shrink-0 items-center gap-0.5 text-xs font-medium text-primary md:inline-flex">
          View
          <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground md:hidden" aria-hidden />
      </Link>
    </li>
  );
}

// ── states ──────────────────────────────────────────────────────────────────

function LoadingBody() {
  return (
    <div aria-busy="true" aria-label="Loading submission reminders">
      <div className="space-y-1 p-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[52px] w-full" />
        ))}
      </div>
    </div>
  );
}

function ErrorBody({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="flex items-center gap-3 px-5 py-6">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
        <TriangleAlert className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">Couldn&apos;t load submission reminders</p>
        <p className="text-xs text-muted-foreground">
          The rest of the dashboard is unaffected. Try again in a moment.
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

function EmptyBody() {
  return (
    <p className="flex items-center gap-2 px-5 py-4 text-sm text-muted-foreground">
      <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden />
      No pending deliverables.
    </p>
  );
}

// ── card ────────────────────────────────────────────────────────────────────

/**
 * PM dashboard "Submission Reminders" - the enhanced Deliverables card.
 *
 * Reuses the cross-project GET /deliverables query (same key and cache as the
 * Deliverables page, invalidated by every deliverable mutation). Rendered only
 * by the PM dashboard; the API itself scopes rows to what the caller may see.
 */
export function SubmissionRemindersCard() {
  const query = useAllDeliverables();
  const items = React.useMemo(() => query.data ?? [], [query.data]);

  const { rows, hidden } = React.useMemo(() => selectReminderRows(items, MAX_ROWS), [items]);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 border-b border-border px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <CalendarClock className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <CardTitle className="truncate text-base">Submission Reminders</CardTitle>
        </div>
        <Button variant="ghost" size="sm" asChild className="shrink-0">
          <Link href="/projects/deliverables">
            View all <ArrowRight className="ml-1 h-3 w-3" />
          </Link>
        </Button>
      </CardHeader>

      <CardContent className="p-0">
        {query.isLoading ? (
          <LoadingBody />
        ) : query.isError ? (
          <ErrorBody onRetry={() => void query.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyBody />
        ) : (
          <>
            <ul className="divide-y divide-border">
              {rows.map((d) => (
                <ReminderRow key={d.id} d={d} />
              ))}
            </ul>

            {hidden > 0 && (
              <Link
                href="/projects/deliverables"
                className="flex items-center justify-center gap-1 border-t border-border px-4 py-2.5 text-xs font-medium text-primary hover:bg-secondary"
              >
                +{hidden} more pending
                <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
