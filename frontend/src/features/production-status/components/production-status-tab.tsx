"use client";

import * as React from "react";
import { ClipboardList, History } from "lucide-react";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { useActivityStaffing } from "@/features/projects/hooks";
import type { Project } from "@/features/projects/types";
import { AppError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";

import { useLatestProductionStatus } from "../hooks";
import {
  buildProductionStatusRows,
  formatProjectPlant,
  NO_STATUS_HINT,
  NO_STATUS_TITLE,
  productionStatusErrorMessage,
  projectActivityOptions,
  submittableActivityOptions,
} from "../production-status";
import { ProductionStatusForm } from "./production-status-form";
import {
  ProductionStatusHistoryDialog,
  type HistoryTarget,
} from "./production-status-history-dialog";
import { ProductionStatusBadge } from "./status-badge";

interface ProductionStatusTabProps {
  /** The project row the page already loaded - the source of Project / Plant. */
  project: Project;
  /** Role-level PM. Full authority over every activity, on every project. */
  canManage: boolean;
  /** This project's assigned Head. Full authority over this project's activities. */
  isHead: boolean;
}

/**
 * Production Status tab - the Project Head / Activity Lead working screen.
 *
 * Two halves, both fed by Phase 1:
 *   the form appends one update (POST /production-status)
 *   the table shows the current status of every revision + activity
 *   (GET /production-status), with a per-row History dialog over
 *   GET /production-status/history.
 *
 * The activity dropdown comes from the project's activity staffing - the same
 * join the backend's `_fetch_valid_activity` accepts against - so the UI can
 * never offer an activity the POST would reject, and no second activity list
 * exists. Which of those the viewer may actually submit for is narrowed by
 * `submittableActivityOptions`, mirroring `authz.activity_staffing_authority`.
 *
 * None of this is the security boundary. Every endpoint re-resolves the same
 * authority server-side; hiding a control is convenience only.
 */
export function ProductionStatusTab({
  project,
  canManage,
  isHead,
}: ProductionStatusTabProps) {
  const { employeeId } = useAuth();
  const [historyTarget, setHistoryTarget] = React.useState<HistoryTarget | null>(null);

  const staffingQuery = useActivityStaffing(project.id);
  const latestQuery = useLatestProductionStatus(project.id);

  const projectPlant = React.useMemo(() => formatProjectPlant(project), [project]);

  const activities = React.useMemo(
    () =>
      submittableActivityOptions(staffingQuery.data, { canManage, isHead, employeeId }),
    [staffingQuery.data, canManage, isHead, employeeId],
  );

  const projectHasActivities =
    projectActivityOptions(staffingQuery.data).length > 0;

  const rows = buildProductionStatusRows(latestQuery.data, formatDateTime);

  // Both requests must land before the form can decide which activities to
  // offer and the table which rows to show.
  if (latestQuery.isLoading || staffingQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-96" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (latestQuery.isError) {
    const status = latestQuery.error instanceof AppError ? latestQuery.error.status : null;
    const message =
      latestQuery.error instanceof AppError ? latestQuery.error.message : null;
    return (
      <Card>
        <CardHeader>
          <CardTitle>Production Status</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState
            title="Couldn't load production status"
            message={productionStatusErrorMessage(status, message)}
            // A 403/404 will not resolve by retrying; anything else might.
            onRetry={
              status === 403 || status === 404
                ? undefined
                : () => void latestQuery.refetch()
            }
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <ProductionStatusForm
        projectId={project.id}
        projectPlant={projectPlant}
        activities={activities}
        projectHasActivities={projectHasActivities}
      />

      <Card>
        <CardHeader>
          <CardTitle>Current Status</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {/* The staffing list is only needed for the dropdown; if it failed
              the current status is still worth showing, so this is a note
              rather than a page-level error. */}
          {staffingQuery.isError && (
            <p className="px-6 pb-4 text-sm text-muted-foreground">
              Couldn&apos;t load this project&apos;s activities, so the Activity list above
              may be incomplete.
            </p>
          )}

          {rows.length === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title={NO_STATUS_TITLE}
              description={NO_STATUS_HINT}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Revision</TableHead>
                  <TableHead>Activity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">TAG</TableHead>
                  <TableHead className="text-right">DOC</TableHead>
                  <TableHead className="text-right">SPARES</TableHead>
                  <TableHead className="text-right">CRS</TableHead>
                  <TableHead>Completed On</TableHead>
                  <TableHead>Remarks</TableHead>
                  <TableHead>By</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.key}>
                    <TableCell className="whitespace-nowrap font-medium">
                      {r.revision}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{r.activity}</TableCell>
                    <TableCell>
                      <ProductionStatusBadge status={r.statusValue ?? r.status} />
                    </TableCell>
                    <TableCell className="text-right tabular">{r.tag}</TableCell>
                    <TableCell className="text-right tabular">{r.doc}</TableCell>
                    <TableCell className="text-right tabular">{r.spares}</TableCell>
                    <TableCell className="text-right tabular">{r.crs}</TableCell>
                    <TableCell className="whitespace-nowrap">{r.completedOn}</TableCell>
                    {/* Line breaks preserved, same as the history dialog. */}
                    <TableCell className="max-w-xs whitespace-pre-wrap">
                      {r.remarks ?? "-"}
                    </TableCell>
                    {/* The real person, straight from the API's created_by_name
                        - never a role word, and never looked up client-side. */}
                    <TableCell className="whitespace-nowrap">{r.by}</TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {r.updated}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setHistoryTarget({
                            activityId: r.activityId,
                            activityLabel: r.activity,
                            revision: r.revision,
                          })
                        }
                      >
                        <History className="h-3.5 w-3.5" />
                        History
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ProductionStatusHistoryDialog
        projectId={project.id}
        target={historyTarget}
        onOpenChange={(open) => {
          if (!open) setHistoryTarget(null);
        }}
      />
    </div>
  );
}
