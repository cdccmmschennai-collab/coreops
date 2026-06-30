"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { CalendarClock, CheckCircle2, RefreshCcw } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import { useDeliverable, useDeliverableChanges } from "../hooks";
import {
  DELIVERABLE_CHANGE_FIELD_LABEL,
  DELIVERABLE_STATUS_LABEL,
  type DeliverableChange,
  type DeliverableStatus,
} from "../types";
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

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
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
                <li key={c.id} className="mb-6 ml-4 last:mb-0">
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
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Reason: {c.reason}
                      </p>
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

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="space-y-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
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
        href="/projects/deliverables"
        className="text-sm text-primary hover:underline"
      >
        ← Deliverables
      </Link>
      <PageHeader
        className="mt-2"
        title={deliverable.name}
        subtitle={deliverable.description ?? undefined}
        actions={<DeliverableStatusBadge status={deliverable.status} />}
      />

      <div className="space-y-4">
        {/* Deliverable info */}
        <Card>
          <CardHeader>
            <CardTitle>Deliverable</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            <InfoRow
              label="Project"
              value={
                <Link
                  href={`/projects/${deliverable.project_id}`}
                  className="text-primary hover:underline"
                >
                  <span className="font-mono">
                    {deliverable.project_code ?? deliverable.project_id}
                  </span>
                  {deliverable.project_name ? (
                    <span className="ml-1 font-normal text-muted-foreground">
                      {deliverable.project_name}
                    </span>
                  ) : null}
                </Link>
              }
            />
            <InfoRow label="Activity" value={deliverable.name} />
            <InfoRow
              label="Planned Submission"
              value={fmtDate(deliverable.target_date)}
            />
          </CardContent>
        </Card>

        {/* Timeline */}
        <Timeline deliverableId={deliverable.id} activityName={deliverable.name} />
      </div>
    </>
  );
}
