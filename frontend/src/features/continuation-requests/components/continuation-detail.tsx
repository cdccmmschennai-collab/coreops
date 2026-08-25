"use client";

import type { ReactNode } from "react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useContinuationRequest } from "../hooks";
import { ContinuationStatusBadge } from "./continuation-status-badge";

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export function ContinuationDetail({ id }: { id: string }) {
  const query = useContinuationRequest(id);

  if (query.isLoading) {
    return (
      <>
        <PageHeader title="Lump-sum Activity Request" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }
  if (query.isError || !query.data) {
    return (
      <>
        <PageHeader title="Lump-sum Activity Request" />
        <ErrorState title="Could not load this request" />
      </>
    );
  }

  const req = query.data;
  return (
    <>
      <PageHeader
        title="Lump-sum Activity Request"
        subtitle={`${req.employee_name} - ${req.project_code || req.project_name}`}
      />
      <Card>
        <CardHeader className="border-b border-border px-5 py-3.5">
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border px-5">
          <InfoRow label="Employee" value={req.employee_name} />
          <InfoRow label="Project" value={`${req.project_code || "-"} - ${req.project_name}`} />
          <InfoRow label="Activity" value={req.activity_name ?? "-"} />
          <InfoRow label="Sub-Activity" value={req.sub_activity_name} />
          <InfoRow label="Original Report" value={req.original_report_date} />
          <InfoRow
            label="Allowed Duration"
            value={`${req.allowed_duration_days} ${req.allowed_duration_days === 1 ? "day" : "days"}`}
          />
          <InfoRow label="Continuation Date" value={req.continuation_date} />
          <InfoRow
            label="Routed To"
            value={
              req.routed_to_name
                ? `${req.routed_to_name} (${req.routed_to_role === "head" ? "Project Head" : "Manager"})`
                : "-"
            }
          />
          <InfoRow label="Status" value={<ContinuationStatusBadge status={req.status} />} />
          {req.reviewer_name && <InfoRow label="Reviewer" value={req.reviewer_name} />}
          {req.decision_comment && (
            <InfoRow label="Decision Comment" value={req.decision_comment} />
          )}
        </CardContent>
      </Card>
    </>
  );
}
