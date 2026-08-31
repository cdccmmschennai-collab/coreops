"use client";

import * as React from "react";
import { ClipboardList, History, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { useActivities } from "@/features/activity-master/hooks";
import { useAuth } from "@/features/auth/auth-provider";
import { useActivityStaffing } from "@/features/projects/hooks";
import type { Project } from "@/features/projects/types";
import { AppError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";

import { useDeleteProductionStatus, useLatestProductionStatus } from "../hooks";
import {
  buildProductionStatusRows,
  canDeleteProductionStatusRow,
  canRecordProductionStatus,
  canTypeNewActivity,
  formatProjectDisplay,
  historyTargetFor,
  maintenancePlantScope,
  NO_STATUS_HINT,
  NO_STATUS_TITLE,
  productionStatusErrorMessage,
  READ_ONLY_HINT,
  READ_ONLY_TITLE,
  submittableActivityOptions,
  type ProductionStatusRow,
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
  /** Role-level PM. Reads every project here - and writes to none of them. */
  canManage: boolean;
  /** This project's assigned Head. Records against any activity, or types one. */
  isHead: boolean;
}

/**
 * Production Status tab - the Project Head / Activity Lead working screen.
 *
 * Two halves:
 *   the form appends one update (POST /production-status)
 *   the table shows the current status of every revision + activity
 *   (GET /production-status), with a per-row History dialog over
 *   GET /production-status/history.
 *
 * Who gets the form, mirroring the backend's `_record_authority`:
 *   the Head   yes - every Activity Master activity, and may type one that is
 *              not in it at all
 *   a Lead     yes - the activities they lead on this project
 *   the PM     NO. The PM reads this tab and downloads the cumulative report;
 *              the updates themselves are made by the people who did the work.
 *
 * The Head's dropdown therefore comes from Activity Master rather than the
 * project's staffing: a project with no staffing still has production to
 * report, and the backend no longer requires an activity to be staffed.
 *
 * None of this is the security boundary. Every endpoint re-resolves the same
 * authority server-side; hiding a control is convenience only.
 */
export function ProductionStatusTab({
  project,
  canManage,
  isHead,
}: ProductionStatusTabProps) {
  const { employeeId, user } = useAuth();
  const [historyTarget, setHistoryTarget] = React.useState<HistoryTarget | null>(null);
  // The row awaiting confirmation. Held rather than a bare boolean so the
  // dialog can name what is about to go.
  const [rowToDelete, setRowToDelete] = React.useState<ProductionStatusRow | null>(null);

  const staffingQuery = useActivityStaffing(project.id);
  const latestQuery = useLatestProductionStatus(project.id);
  const deleteMutation = useDeleteProductionStatus(project.id);

  const viewer = React.useMemo(
    () => ({ canManage, isHead, employeeId }),
    [canManage, isHead, employeeId],
  );

  // Whether the viewer may write at all - decided from the project's staffing
  // and their Head flag, never from the role. A PM is deliberately not a writer
  // here.
  const canRecord = canRecordProductionStatus(staffingQuery.data, viewer);

  // Activity Master, for the Head's dropdown. The SAME shared hook the Activity
  // Master screen uses over the same endpoint - no second activity list exists.
  // Only fetched for someone who can actually record: a PM reading the tab must
  // not pay for a list they will never see.
  const activityMasterQuery = useActivities(true);
  const activityMaster = canRecord ? activityMasterQuery.data : undefined;

  const projectDisplay = React.useMemo(() => formatProjectDisplay(project), [project]);

  const activities = React.useMemo(
    () => submittableActivityOptions(staffingQuery.data, activityMaster, viewer),
    [staffingQuery.data, activityMaster, viewer],
  );

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
      {canRecord ? (
        <ProductionStatusForm
          projectId={project.id}
          projectDisplay={projectDisplay}
          // The project's Planning Plant scopes which Maintenance Plants the
          // form may offer — exactly as it does on the Project Edit page.
          planningPlantCode={maintenancePlantScope(project)}
          activities={activities}
          canTypeActivity={canTypeNewActivity(viewer)}
        />
      ) : (
        // The PM's view of this tab, and anyone else with read authority: the
        // current status below, and no form. Stated plainly rather than left as
        // a missing card, so it reads as a rule and not as something broken.
        <Card>
          <CardHeader>
            <CardTitle>Production Status</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium text-foreground">{READ_ONLY_TITLE}</p>
            <p className="mt-0.5 text-sm text-muted-foreground">{READ_ONLY_HINT}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Current Status</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {/* The staffing list is only needed for a Lead's dropdown; if it
              failed the current status is still worth showing, so this is a
              note rather than a page-level error. */}
          {canRecord && staffingQuery.isError && (
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
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          // The trail is this ROW's revision + activity, so the
                          // dialog can only ever show that one combination.
                          onClick={() => setHistoryTarget(historyTargetFor(r))}
                        >
                          <History className="h-3.5 w-3.5" />
                          History
                        </Button>
                        {/* Shown only to the person who recorded THIS row. The
                            backend re-resolves the same ownership, so this is
                            tidiness rather than the control. */}
                        {canDeleteProductionStatusRow(r, user?.id) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => setRowToDelete(r)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </Button>
                        )}
                      </div>
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

      {/* The same AlertDialog confirmation every other destructive action in
          CoreOps uses (see submissions-tab, deliverables-tab). */}
      <AlertDialog
        open={!!rowToDelete}
        onOpenChange={(open) => {
          if (!open && !deleteMutation.isPending) setRowToDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this production status record?</AlertDialogTitle>
            <AlertDialogDescription>
              {rowToDelete
                ? `The ${rowToDelete.revision} update you recorded for ${rowToDelete.activity} will be permanently removed. If an earlier update exists for it, that one becomes the current status again.`
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <Button
              variant="danger"
              loading={deleteMutation.isPending}
              onClick={async () => {
                if (!rowToDelete) return;
                try {
                  await deleteMutation.mutateAsync(rowToDelete.key);
                  setRowToDelete(null);
                  toast.success("Production status record deleted");
                } catch (err) {
                  // The module's own error wording, so a 403 from a record that
                  // is not the caller's reads the same here as anywhere else.
                  const status = err instanceof AppError ? err.status : null;
                  const message = err instanceof AppError ? err.message : null;
                  toast.error(productionStatusErrorMessage(status, message));
                }
              }}
            >
              Delete
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
