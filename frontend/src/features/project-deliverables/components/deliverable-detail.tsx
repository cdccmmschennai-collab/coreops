"use client";

import * as React from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarClock, CheckCircle2, Pencil, RefreshCcw, Trash2 } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import { useProject } from "@/features/projects/hooks";

import { cn } from "@/lib/utils";

import {
  PROJECT_HEAD_TEXT,
  assigneeDisplay,
  daysLeftLabel,
  projectHeadDisplay,
  projectHref,
  projectLabel,
} from "../detail-view";
import { useDeliverable, useDeliverableChanges } from "../hooks";
import { DELIVERABLE_RETURN_PARAM, deliverableReturnHref } from "../list-filters";
import {
  DELIVERABLE_CHANGE_FIELD_LABEL,
  DELIVERABLE_STATUS_LABEL,
  type DeadlineState,
  type Deliverable,
  type DeliverableChange,
  type DeliverableStatus,
} from "../types";
import { canManageRow } from "../manage-access";
import { leaveDetail } from "../return-nav";
import { DeleteDeliverableDialog, DeliverableFormPanel } from "./all-deliverables-view";
import { DeliverableStatusBadge } from "./status-badge";

// ── date helpers ───────────────────────────────────────────────────────────────

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = m
    ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
    : new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtDateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderChangeValue(field: string, value: string | null): string {
  if (value === null) return "—";
  if (field === "status") {
    return DELIVERABLE_STATUS_LABEL[value as DeliverableStatus] ?? value;
  }
  return fmtDate(value);
}

// ── info row ────────────────────────────────────────────────────────────────────

/** Label column fixed on sm+, label above value on narrow screens. */
function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-0.5 py-2.5 text-sm sm:grid-cols-[9rem_minmax(0,1fr)]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

// ── timeline (change history, answers what / why / who) ──────────────────────────

function Timeline({
  deliverableId,
  activityName,
}: {
  deliverableId: string;
  activityName: string;
}) {
  const query = useDeliverableChanges(deliverableId);
  const changes: DeliverableChange[] = query.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((n) => (
              <Skeleton key={n} className="h-10 w-full" />
            ))}
          </div>
        ) : changes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No changes recorded yet.</p>
        ) : (
          <ol className="relative border-l border-border">
            {changes.map((c) => {
              const isCompletion =
                c.field === "status" && c.new_value === "completed";
              const label = DELIVERABLE_CHANGE_FIELD_LABEL[c.field] ?? c.field;
              const icon = isCompletion ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              ) : c.field === "status" ? (
                <RefreshCcw className="h-3.5 w-3.5" />
              ) : (
                <CalendarClock className="h-3.5 w-3.5" />
              );
              return (
                <li key={c.id} className="mb-6 ml-4 min-w-0 break-words last:mb-0">
                  <span className="absolute -left-[1.1rem] flex h-[1.4rem] w-[1.4rem] items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
                    {icon}
                  </span>
                  {isCompletion ? (
                    <p className="text-sm font-medium">
                      {activityName} has been delivered.
                    </p>
                  ) : (
                    <>
                      <p className="text-sm font-medium">
                        {label} changed {renderChangeValue(c.field, c.old_value)} →{" "}
                        {renderChangeValue(c.field, c.new_value)}
                      </p>
                      {c.reason ? (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          Reason: {c.reason}
                        </p>
                      ) : null}
                    </>
                  )}
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {c.changed_by_name || "System"} · {fmtDateTime(c.changed_at)}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

// ── page ────────────────────────────────────────────────────────────────────────

export function DeliverableDetail({ id }: { id: string }) {
  const query = useDeliverable(id);
  const deliverable = query.data;
  // "← Deliverables" returns to the exact list state it was opened from
  // (filters + page, via `?from=`); a cold/deep link falls back to the list.
  const backHref = deliverableReturnHref(
    useSearchParams().get(DELIVERABLE_RETURN_PARAM),
  );
  const router = useRouter();
  // Edit happens IN PLACE (no navigation), so it never adds a history entry.
  const [editing, setEditing] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<Deliverable | null>(null);

  // Back link and post-delete exit: history.back() when the list is behind
  // us, else replace - so Back never loops between details and the list.
  function goBack() {
    leaveDetail(id, backHref, router);
  }

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </>
    );
  }

  if (query.isError || !deliverable) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Deliverable not found" : "Couldn't load deliverable"}
        message={
          notFound
            ? "This deliverable may have been removed."
            : "Please try again."
        }
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  return (
    <>
      <Link
        href={backHref}
        className="text-sm text-primary hover:underline"
        onClick={(e) => {
          // Plain click: leave without growing history. Modified clicks
          // (new tab / window) keep the normal link behaviour.
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          goBack();
        }}
      >
        ← Deliverables
      </Link>
      <PageHeader
        className="mt-2"
        title={deliverable.name}
        subtitle={deliverable.description ?? undefined}
        actions={
          <div className="flex items-center gap-1">
            {/* Same Edit / Delete controls as the table's Actions column, to
                the left of the status badge; PM / project Head only. */}
            {canManageRow(deliverable) && !editing && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Edit"
                  onClick={() => setEditing(true)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Delete"
                  onClick={() => setPendingDelete(deliverable)}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </>
            )}
            <DeliverableStatusBadge status={deliverable.status} />
          </div>
        }
      />

      {editing ? (
        // The list page's own form; saving refreshes this page's details and
        // timeline (same query invalidation) and returns to the view.
        <DeliverableFormPanel
          editing={deliverable}
          projectOptions={[]}
          onDone={() => setEditing(false)}
        />
      ) : (
        /* Two columns on desktop (details | timeline), stacked on mobile with
           details first - DOM order is the mobile order. */
        <div
          data-testid="deliverable-detail-grid"
          className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2"
        >
          <div className="min-w-0">
            <DetailsCard deliverable={deliverable} />
          </div>
          <div className="min-w-0">
            <Timeline deliverableId={deliverable.id} activityName={deliverable.name} />
          </div>
        </div>
      )}

      <DeleteDeliverableDialog
        target={pendingDelete}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        onDeleted={() => {
          setPendingDelete(null);
          goBack();
        }}
      />
    </>
  );
}

// ── left column: deliverable details ───────────────────────────────────────────

/** Same tone ladder as the PM reminder rows; the state comes from the backend. */
const DAYS_LEFT_TONE: Record<DeadlineState, string> = {
  overdue: "border-destructive/30 bg-destructive/[0.06] text-destructive font-semibold",
  due_today: "border-warning/30 bg-warning/[0.08] text-warning font-semibold",
  urgent: "border-warning/30 bg-warning/[0.08] text-warning font-semibold",
  due_soon: "border-warning/25 bg-warning/[0.05] text-warning font-medium",
  on_track: "border-border bg-muted/40 text-muted-foreground font-medium",
  no_deadline: "border-border text-muted-foreground",
  completed: "border-border text-muted-foreground",
};

function DetailsCard({ deliverable }: { deliverable: Deliverable }) {
  // Same GET /projects/{id} query (and cache) the Project Detail page uses; the
  // backend gates it with the same can_view_project check as this deliverable.
  const projectQuery = useProject(deliverable.project_id);
  const head = projectHeadDisplay(projectQuery);
  const project = projectLabel(deliverable);
  const daysLeft = daysLeftLabel(deliverable);
  // Same helper as the Deliverables table, from the same GET /deliverables/{id}
  // row (invalidated on every update), so the two always agree.
  const assignee = assigneeDisplay(deliverable);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle>Deliverable Details</CardTitle>
        {daysLeft ? (
          <span
            data-testid="deliverable-days-left"
            className={cn(
              "shrink-0 rounded-full border px-2.5 py-0.5 text-xs tabular",
              DAYS_LEFT_TONE[deliverable.deadline_state],
            )}
          >
            {daysLeft}
          </span>
        ) : null}
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border">
          <InfoRow label="Project">
            <Link
              href={projectHref(deliverable.project_id)}
              className="font-semibold text-primary hover:underline"
            >
              {project.number}
            </Link>
            {project.description ? (
              <p className="mt-0.5 break-words text-xs text-muted-foreground">
                {project.description}
              </p>
            ) : null}
          </InfoRow>
          <InfoRow label="Assignee">
            {assignee.assigned ? (
              <span data-testid="deliverable-assignee" className="font-medium">
                {assignee.name}
              </span>
            ) : (
              <span data-testid="deliverable-assignee" className="text-muted-foreground">
                Unassigned
              </span>
            )}
          </InfoRow>
          <InfoRow label="Project Head">
            {head.kind === "loading" ? (
              <Skeleton className="h-5 w-32" aria-label="Loading Project Head" />
            ) : head.kind === "assigned" ? (
              <span className="font-medium">{head.name}</span>
            ) : (
              <span className="text-muted-foreground">{PROJECT_HEAD_TEXT[head.kind]}</span>
            )}
          </InfoRow>
          <InfoRow label="Activity">
            <span className="break-words font-semibold">{deliverable.name}</span>
          </InfoRow>
          <InfoRow label="Planned Submission">
            <span className="font-semibold tabular">{fmtDate(deliverable.target_date)}</span>
          </InfoRow>
          {deliverable.status === "completed" && deliverable.completion_date ? (
            <InfoRow label="Actual Submission">
              <span className="font-semibold tabular">
                {fmtDate(deliverable.completion_date)}
              </span>
            </InfoRow>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}
